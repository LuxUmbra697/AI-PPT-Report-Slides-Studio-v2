import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router'
import { useAuthStore } from '@/features/auth/store'

export function RequireAuth({ children }: { children: ReactNode }) {
  const user = useAuthStore((state) => state.user)
  const restoring = useAuthStore((state) => state.restoring)
  const location = useLocation()

  // 刷新页面时本地有 token 但用户信息还没换回来，
  // 此时不能判定为未登录，否则会闪一下登录页再跳回来。
  if (restoring) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-ink-muted">
        正在恢复登录状态…
      </div>
    )
  }

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }

  return children
}
