import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  addExpenseAttachment,
  approveExpenseReport,
  createExpenseReport,
  deleteExpenseAttachment,
  deleteExpenseReport,
  getExpenseReport,
  listExpenseOptions,
  listMyExpenseReports,
  listSubmittedExpenseReports,
  returnExpenseReport,
  saveExpenseReportLines,
  submitExpenseReport,
  type ExpenseLineChange,
  type ExpenseScope,
} from "@/expenses/api";

export const expenseKeys = {
  all: ["expenses"] as const,
  options: () => [...expenseKeys.all, "options"] as const,
  // A shared prefix, for invalidating every cached report and list at once.
  allReports: () => [...expenseKeys.all, "report"] as const,
  reports: (userId: string, year: number, month: number) =>
    [...expenseKeys.allReports(), "list", userId, year, month] as const,
  report: (reportId: string) => [...expenseKeys.allReports(), reportId] as const,
  allSubmissions: () => [...expenseKeys.all, "submissions"] as const,
  submissions: (scope?: ExpenseScope) => [...expenseKeys.allSubmissions(), scope] as const,
};

export function useExpenseOptions() {
  return useQuery({
    queryKey: expenseKeys.options(),
    queryFn: listExpenseOptions,
  });
}

/** `userId` selects whose reports to load; pass the viewer's own id for "my expenses". */
export function useMyExpenseReports(userId: string, year: number, month: number) {
  return useQuery({
    queryKey: expenseKeys.reports(userId, year, month),
    queryFn: () => listMyExpenseReports({ year, month, userId }),
  });
}

export function useExpenseReport(reportId: string) {
  return useQuery({
    queryKey: expenseKeys.report(reportId),
    queryFn: () => getExpenseReport(reportId),
  });
}

/** Start a new draft report; the caller navigates to it on success. */
export function useCreateExpenseReport() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createExpenseReport,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: expenseKeys.allReports() });
    },
  });
}

export function useSaveExpenseReportLines(reportId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      lines,
      deleteLineIds = [],
    }: {
      lines: ExpenseLineChange[];
      deleteLineIds?: string[];
    }) => saveExpenseReportLines(reportId, lines, deleteLineIds),
    onSuccess: (report) => {
      queryClient.setQueryData(expenseKeys.report(reportId), report);
      void queryClient.invalidateQueries({ queryKey: expenseKeys.allReports() });
    },
  });
}

export function useDeleteExpenseReport(reportId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => deleteExpenseReport(reportId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: expenseKeys.allReports() });
    },
  });
}

export function useSubmitExpenseReport(reportId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => submitExpenseReport(reportId),
    onSuccess: (report) => {
      queryClient.setQueryData(expenseKeys.report(reportId), report);
      void queryClient.invalidateQueries({ queryKey: expenseKeys.allReports() });
      void queryClient.invalidateQueries({ queryKey: expenseKeys.allSubmissions() });
    },
  });
}

export function useApproveExpenseReport(reportId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => approveExpenseReport(reportId),
    onSuccess: (report) => {
      queryClient.setQueryData(expenseKeys.report(reportId), report);
      void queryClient.invalidateQueries({ queryKey: expenseKeys.allReports() });
      void queryClient.invalidateQueries({ queryKey: expenseKeys.allSubmissions() });
    },
  });
}

export function useReturnExpenseReport(reportId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (comment: string) => returnExpenseReport({ reportId, comment }),
    onSuccess: (report) => {
      queryClient.setQueryData(expenseKeys.report(reportId), report);
      void queryClient.invalidateQueries({ queryKey: expenseKeys.allReports() });
      void queryClient.invalidateQueries({ queryKey: expenseKeys.allSubmissions() });
    },
  });
}

/** The manager's Expenses tab of `/approvals`: reports awaiting review. `scope: "mine"` narrows
 * to projects the caller manages. */
export function useSubmittedExpenseReports(scope?: ExpenseScope) {
  return useQuery({
    queryKey: expenseKeys.submissions(scope),
    queryFn: () => listSubmittedExpenseReports({ scope }),
  });
}

export function useAddExpenseAttachment(reportId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (params: { file: File; fileName?: string }) =>
      addExpenseAttachment({ reportId, ...params }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: expenseKeys.report(reportId) });
    },
  });
}

export function useDeleteExpenseAttachment(reportId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (attachmentId: string) => deleteExpenseAttachment(attachmentId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: expenseKeys.report(reportId) });
    },
  });
}
