import { request } from '@/api/client'
import type { components } from '@/api/schema'

type Schemas = components['schemas']

export type UserPublic = Schemas['UserPublic']
export type TokenResponse = Schemas['TokenResponse']
/** login / register 请求体字段一致，统一用 LoginRequest */
export type Credentials = Schemas['LoginRequest']

export function register(payload: Credentials) {
  return request<TokenResponse>('/auth/register', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function login(payload: Credentials) {
  return request<TokenResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function fetchCurrentUser() {
  return request<UserPublic>('/auth/me')
}
