const STORAGE_KEY = 'luxumbra.token'

/**
 * token 的唯一持有处。单独成模块是为了让请求层和状态层都能读它，
 * 而不必互相 import 造成循环依赖。
 */
export const tokenStore = {
  get(): string | null {
    return localStorage.getItem(STORAGE_KEY)
  },
  set(token: string) {
    localStorage.setItem(STORAGE_KEY, token)
  },
  clear() {
    localStorage.removeItem(STORAGE_KEY)
  },
}
