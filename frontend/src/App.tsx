import { useEffect } from 'react'
import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router'
import { AppShell } from '@/components/AppShell'
import { AnimeDecorLayer } from '@/components/AnimeDecorLayer'
import { MascotCompanion } from '@/components/MascotCompanion'
import { useAuthStore } from '@/features/auth/store'
import { UiThemeProvider } from '@/features/ui/UiThemeContext'
import AuthPage from '@/pages/AuthPage'
import CreatePage from '@/pages/CreatePage'
import ProjectDetailPage from '@/pages/ProjectDetailPage'
import ProjectsPage from '@/pages/ProjectsPage'
import { RequireAuth } from '@/routes/RequireAuth'

export default function App() {
  const restore = useAuthStore((state) => state.restore)

  useEffect(() => {
    void restore()
  }, [restore])

  return (
    <BrowserRouter>
      <UiThemeProvider>
        <div className="anime-app">
          <Routes>
            <Route path="/login" element={<AuthPage />} />

            <Route
              element={
                <RequireAuth>
                  <AppShell>
                    <Outlet />
                  </AppShell>
                </RequireAuth>
              }
            >
              <Route path="/projects" element={<ProjectsPage />} />
              <Route path="/create" element={<CreatePage />} />
            </Route>

            {/* 大纲与编辑工作台自带全屏 chrome，不进工作区外壳 */}
            <Route
              element={
                <RequireAuth>
                  <Outlet />
                </RequireAuth>
              }
            >
              <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
            </Route>

            <Route path="*" element={<Navigate to="/projects" replace />} />
          </Routes>
          <AnimeDecorLayer />
          <MascotCompanion />
        </div>
      </UiThemeProvider>
    </BrowserRouter>
  )
}
