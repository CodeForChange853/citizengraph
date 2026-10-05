import { QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "motion/react";
import { lazy, Suspense, useState } from "react";
import { BrowserRouter, Route, Routes } from "react-router";
import { ApiProvider } from "./api/ApiProvider";
import { createQueryClient } from "./api/queryClient";
import { Shell } from "./components/Shell";
import { LoadGuard } from "./landing/LoadGuard";
import Chat from "./routes/Chat";
import Home from "./routes/Home";
import Help from "./routes/Help";
import Saved from "./routes/Saved";

// The design page is a developer tool: load it only when opened.
const Design = lazy(() => import("./routes/Design"));
// The animated introduction is heavy and optional: its own chunk, outside the shell.
const Landing = lazy(() => import("./routes/Landing"));

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route path="/" element={<Home />} />
        <Route path="/chat" element={<Chat />} />
        <Route path="/saved" element={<Saved />} />
        <Route path="/help" element={<Help />} />
      </Route>
      <Route
        path="/welcome"
        element={
          <LoadGuard>
            <Suspense fallback={null}>
              <Landing />
            </Suspense>
          </LoadGuard>
        }
      />
      <Route
        path="/design"
        element={
          <Suspense fallback={null}>
            <Design />
          </Suspense>
        }
      />
    </Routes>
  );
}

export default function App() {
  const [queryClient] = useState(() => createQueryClient());
  return (
    <QueryClientProvider client={queryClient}>
      <ApiProvider>
        {/* reducedMotion="user": motion respects the phone's "reduce motion" setting */}
        <MotionConfig reducedMotion="user">
          <BrowserRouter>
            <AppRoutes />
          </BrowserRouter>
        </MotionConfig>
      </ApiProvider>
    </QueryClientProvider>
  );
}
