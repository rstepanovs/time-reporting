import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  addNonWorkingDay,
  deleteNonWorkingDay,
  getCalendarDays,
  importPublicHolidays,
  listNonWorkingDays,
  type NonWorkingDayKind,
  updateNonWorkingDay,
} from "@/calendar/api";

export const calendarKeys = {
  all: ["calendar"] as const,
  days: (range: { from: string; to: string }) => [...calendarKeys.all, "days", range] as const,
  nonWorkingDays: (year?: number) => [...calendarKeys.all, "non-working-days", year] as const,
};

export function useCalendarDays(range: { from: string; to: string }) {
  return useQuery({
    queryKey: calendarKeys.days(range),
    queryFn: () => getCalendarDays(range),
  });
}

export function useNonWorkingDays(year?: number) {
  return useQuery({
    queryKey: calendarKeys.nonWorkingDays(year),
    queryFn: () => listNonWorkingDays(year),
  });
}

export function useAddNonWorkingDay() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { day: string; name: string; kind: NonWorkingDayKind }) =>
      addNonWorkingDay(body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: calendarKeys.all }),
  });
}

export function useUpdateNonWorkingDay(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { day?: string; name?: string }) => updateNonWorkingDay(id, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: calendarKeys.all }),
  });
}

export function useDeleteNonWorkingDay() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteNonWorkingDay(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: calendarKeys.all }),
  });
}

export function useImportPublicHolidays() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (year: number) => importPublicHolidays(year),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: calendarKeys.all }),
  });
}
