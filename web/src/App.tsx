import React, { Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Login } from './pages/Login';
import { Dashboard } from './pages/Dashboard';

const Preview = lazy(() => import('./pages/Preview'));

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<Dashboard />} />
        <Route
          path="/elr/:elr"
          element={
            <Suspense
              fallback={
                <div className="min-h-screen bg-slate-50 flex items-center justify-center text-slate-500 text-sm">
                  Loading ELR Preview...
                </div>
              }
            >
              <Preview />
            </Suspense>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
};
export default App;
