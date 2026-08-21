import {
  createBrowserRouter,
  RouterProvider,
  Navigate,
  Outlet,
} from 'react-router-dom'
import { useAuth } from './auth/AuthContext'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import BucketList from './pages/Buckets/BucketList'
import SubscriptionList from './pages/Subscriptions/SubscriptionList'
import InsuranceList from './pages/Insurances/InsuranceList'
import UserList from './pages/Users/UserList'
import Chat from './pages/Chat'
import Settings from './pages/Settings'
import ImportHub from './pages/Import/ImportHub'
import Search from './pages/Search'
import AuthCallback from './pages/AuthCallback'

// ---------------------------------------------------------------------------
// RequireAuth — shows a spinner while auth is initialising; once resolved,
// either renders the app (authenticated) or waits while AuthContext redirects
// to Keycloak (unauthenticated).
// ---------------------------------------------------------------------------

function RequireAuth() {
  const { isLoading, isAuthenticated } = useAuth()

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
          <p className="text-sm text-gray-400">Loading…</p>
        </div>
      </div>
    )
  }

  // Not authenticated — AuthContext is already calling signinRedirect().
  // Render nothing while the browser navigates to Keycloak.
  if (!isAuthenticated) return null

  return <Outlet />
}

// ---------------------------------------------------------------------------
// RequireAdmin — redirects non-admin users to the dashboard.
// ---------------------------------------------------------------------------

function RequireAdmin() {
  const { user } = useAuth()
  if (!user?.is_admin) return <Navigate to="/" replace />
  return <Outlet />
}

// ---------------------------------------------------------------------------
// Router
// ---------------------------------------------------------------------------

const router = createBrowserRouter([
  // OIDC callback — outside Layout and auth guard, no token exists yet
  {
    path: '/auth/callback',
    element: <AuthCallback />,
  },

  // All authenticated routes wrapped in RequireAuth
  {
    element: <RequireAuth />,
    children: [
      {
        path: '/',
        element: <Layout />,
        children: [
          { index: true, element: <Dashboard /> },
          { path: 'buckets', element: <BucketList /> },
          {
            path: 'buckets/:bucketId/subscriptions',
            element: <SubscriptionList />,
          },
          {
            path: 'buckets/:bucketId/insurances',
            element: <InsuranceList />,
          },
          {
            path: 'subscriptions',
            element: <Navigate to="/buckets" replace />,
          },
          { path: 'search', element: <Search /> },
          { path: 'chat', element: <Chat /> },
          { path: 'import', element: <ImportHub /> },
          // Admin-only routes
          {
            element: <RequireAdmin />,
            children: [
              { path: 'users', element: <UserList /> },
              { path: 'settings', element: <Settings /> },
            ],
          },
        ],
      },
    ],
  },
])

export function AppRouter() {
  return <RouterProvider router={router} />
}
