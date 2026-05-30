/**
 * AuthContext — provides current user and auth state to the whole app.
 *
 * In development (DEV_MODE detected by the app returning a user without a token),
 * authentication is treated as always-passing.
 *
 * In production the OIDC flow (via oidc-client-ts) handles login/logout.
 */

import { createContext, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { usersApi } from '../api/users'
import type { User } from '../types'

interface AuthContextValue {
  user: User | null
  isLoading: boolean
  isAuthenticated: boolean
  login: () => void
  logout: () => void
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  isLoading: true,
  isAuthenticated: false,
  login: () => {},
  logout: () => {},
})

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    // Attempt to load the current user.
    // In DEV_MODE the backend returns the dummy user without any token.
    usersApi.me()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setIsLoading(false))
  }, [])

  const login = async () => {
    try {
      const u = await usersApi.login()
      setUser(u)
    } catch (err) {
      console.error('Login failed', err)
    }
  }

  const logout = () => {
    setUser(null)
    // In production: clear OIDC session
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated: user !== null,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  return useContext(AuthContext)
}
