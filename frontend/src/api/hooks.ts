import { useMutation, useQuery } from "@tanstack/react-query";
import { useApi } from "./ApiProvider";
import type { ChatRequest } from "./types";

export function useServices() {
  const api = useApi();
  return useQuery({ queryKey: ["services"], queryFn: () => api.services(), staleTime: 5 * 60_000 });
}

export function useChat() {
  const api = useApi();
  return useMutation({ mutationFn: (req: ChatRequest) => api.chat(req) });
}
