"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, projectsApi, type Project } from "@/lib/api";

export function useProjects() {
  return useQuery({ queryKey: ["projects"], queryFn: projectsApi.list });
}

export function useProject(id: string) {
  return useQuery({
    queryKey: ["projects", id],
    queryFn: () => projectsApi.get(id),
    enabled: !!id,
  });
}

export function useEndpoint<T>(key: unknown[], path: string, enabled = true) {
  return useQuery<T>({ queryKey: key, queryFn: () => api<T>(path), enabled });
}

export function useProjectUpdate(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (
      body: Partial<Pick<Project, "title" | "description" | "language">>,
    ) => projectsApi.update(id, body),
    onSuccess: (project) => {
      queryClient.setQueryData(["projects", id], project);
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}
