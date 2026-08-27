import { create } from 'zustand'
import { fetchCurrentUser, type TokenResponse, type UserPublic } from '@/features/auth/api'
import { tokenStore } from '@/features/auth/token'

interface AuthState {
  user: UserPublic | null
  /** 首屏用本地 token 换取用户信息期间为 true，用于避免受保护路由误判为未登录 */
  restoring: boolean
  applySession: (session: TokenResponse) => void
  restore: () => Promise<void>
  logout: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  restoring: tokenStore.get() !== null,

  applySession: (session) => {
    tokenStore.set(session.access_token)
    set({ user: session.user, restoring: false })
  },

  restore: async () => {
    if (tokenStore.get() === null) {
      set({ user: null, restoring: false })
      return
    }
    try {
      set({ user: await fetchCurrentUser(), restoring: false })
    } catch {
      // token 已失效，请求层会清理它，这里只需回到未登录态
      set({ user: null, restoring: false })
    }
  },

  logout: () => {
    tokenStore.clear()
    set({ user: null, restoring: false })
  },
}))
