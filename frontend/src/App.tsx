import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "motion/react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { BrowserRouter, Route, Routes } from "react-router";
import { ApiProvider } from "./api/ApiProvider";
import { Shell } from "./components/Shell";
import Chat from "./routes/Chat";
import Design from "./routes/Design";
import Home from "./routes/Home";
import Placeholder from "./routes/Placeholder";

export function AppRoutes() {
  const { t } = useTranslation();
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route path="/" element={<Home />} />
        <Route path="/chat" element={<Chat />} />
        <Route path="/saved" element={<Placeholder title={t("nav.saved")} />} />
        <Route path="/help" element={<Placeholder title={t("nav.help")} />} />
      </Route>
      <Route path="/design" element={<Design />} />
    </Routes>
  );
}

export default function App() {
  const [queryClient] = useState(() => new QueryClient({ defaultOptions: { queries: { retry: 1 } } }));
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
