
import {
  createBrowserRouter,
  RouterProvider,
  Navigate,
} from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import BucketList from './pages/Buckets/BucketList'
import SubscriptionList from './pages/Subscriptions/SubscriptionList'
import UserList from './pages/Users/UserList'
import Chat from './pages/Chat'
import Settings from './pages/Settings'
import ImportHub from './pages/Import/ImportHub'
import Search from './pages/Search'

const router = createBrowserRouter([
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
      // Alias: /subscriptions navigates to buckets for bucket selection
      {
        path: 'subscriptions',
        element: <Navigate to="/buckets" replace />,
      },
      { path: 'users', element: <UserList /> },
      { path: 'search', element: <Search /> },
      { path: 'chat', element: <Chat /> },
      { path: 'settings', element: <Settings /> },
      { path: 'import', element: <ImportHub /> },
    ],
  },
])

export function AppRouter() {
  return <RouterProvider router={router} />
}
