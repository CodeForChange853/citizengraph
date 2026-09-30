import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "motion/react";
import { useState } from "react";
import { BrowserRouter, Route, Routes } from "react-router";
import { ApiProvider } from "./api/ApiProvider";
import Design from "./routes/Design";
import Home from "./routes/Home";

export default function App() {
  const [queryClient] = useState(() => new QueryClient({ defaultOptions: { queries: { retry: 1 } } }));
  return (
    <QueryClientProvider client={queryClient}>
      <ApiProvider>
        {/* reducedMotion="user": motion respects the phone's "reduce motion" setting */}
        <MotionConfig reducedMotion="user">
          <BrowserRouter>
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/design" element={<Design />} />
            </Routes>
          </BrowserRouter>
        </MotionConfig>
      </ApiProvider>
    </QueryClientProvider>
  );
}
