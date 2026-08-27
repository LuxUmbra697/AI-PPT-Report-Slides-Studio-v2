import { type FormEvent, useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router'
import { BrandMark } from '@/components/BrandMark'
import { Button } from '@/components/ui/Button'
import { TextField } from '@/components/ui/TextField'
import { login, register } from '@/features/auth/api'
import { useAuthStore } from '@/features/auth/store'
import { errorMessage } from '@/lib/errors'

type Mode = 'login' | 'register'

const COPY: Record<Mode, { title: string; submit: string; switchHint: string; switchTo: string }> =
  {
    login: {
      title: '欢迎回来',
      submit: '登录',
      switchHint: '还没有账号？',
      switchTo: '注册一个',
    },
    register: {
      title: '创建账号',
      submit: '注册并开始',
      switchHint: '已经有账号了？',
      switchTo: '去登录',
    },
  }

export default function AuthPage() {
  const [mode, setMode] = useState<Mode>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const user = useAuthStore((state) => state.user)
  const restoring = useAuthStore((state) => state.restoring)
  const applySession = useAuthStore((state) => state.applySession)
  const navigate = useNavigate()
  const location = useLocation()

  // 有本地 token 时先等 restore，避免已登录用户闪一下登录表单
  if (restoring) {
    return (
      <div className="grid min-h-screen place-items-center text-sm text-ink-muted">
        正在恢复登录状态…
      </div>
    )
  }

  if (user) {
    return <Navigate to="/projects" replace />
  }

  const copy = COPY[mode]

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      const session = await (mode === 'login' ? login : register)({ email, password })
      applySession(session)
      const from = (location.state as { from?: string } | null)?.from ?? '/projects'
      navigate(from, { replace: true })
    } catch (cause) {
      setError(errorMessage(cause instanceof Error ? cause : null, '网络异常，请稍后重试'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="bg-aurora flex min-h-screen items-center justify-center px-6 py-16">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <BrandMark className="mx-auto mb-5 size-11 shadow-card" />
          <h1 className="text-2xl font-semibold tracking-tight">{copy.title}</h1>
          <p className="mt-2 text-sm text-ink-muted">
            把一段想法变成可以直接编辑的 16:9 PPT
          </p>
        </div>

        <div className="rounded-3xl border border-line bg-surface p-6 shadow-card">
          <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate>
            <TextField
              label="邮箱"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@example.com"
              autoComplete="email"
              required
            />
            <TextField
              label="密码"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="至少 8 位"
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              minLength={8}
              required
            />

            {error && (
              <p role="alert" className="rounded-xl bg-negative/8 px-3.5 py-2.5 text-[13px] text-negative">
                {error}
              </p>
            )}

            <Button type="submit" size="lg" disabled={submitting} className="mt-1 w-full">
              {submitting ? '处理中…' : copy.submit}
            </Button>
          </form>
        </div>

        <p className="mt-6 text-center text-sm text-ink-muted">
          {copy.switchHint}
          <button
            type="button"
            onClick={() => {
              setMode(mode === 'login' ? 'register' : 'login')
              setError(null)
            }}
            className="ml-1 font-medium text-accent underline-offset-4 transition-colors hover:underline"
          >
            {copy.switchTo}
          </button>
        </p>
      </div>
    </div>
  )
}
