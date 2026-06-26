import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createWorkUnit,
  listWorkUnits,
  updateWorkUnit,
  type CreateWorkUnitRequest,
  type UpdateWorkUnitRequest,
} from "./api";

export function useWorkUnits(options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: ["work-units"],
    queryFn: () => listWorkUnits({ limit: 500 }),
    enabled: options.enabled ?? true,
    refetchInterval: 10_000,
    refetchOnWindowFocus: true,
  });
}

export function useCreateWorkUnit() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: CreateWorkUnitRequest) => createWorkUnit(request),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["work-units"] });
    },
  });
}

export function useUpdateWorkUnit() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      workUnitId,
      request,
    }: {
      workUnitId: string;
      request: UpdateWorkUnitRequest;
    }) => updateWorkUnit(workUnitId, request),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["work-units"] });
    },
  });
}
