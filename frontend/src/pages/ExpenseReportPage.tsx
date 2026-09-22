import { Alert, Anchor, Badge, Button, Group, Loader, Modal, Stack, Text, Textarea, Title } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { AttachmentsCard } from "@/expenses/AttachmentsCard";
import {
  ExpenseConflictError,
  ExpenseRuleError,
  type ExpenseReportStatus,
} from "@/expenses/api";
import { ExpenseLinesTable } from "@/expenses/ExpenseLinesTable";
import {
  useApproveExpenseReport,
  useDeleteExpenseReport,
  useExpenseOptions,
  useExpenseReport,
  useReturnExpenseReport,
} from "@/expenses/hooks";

const STATUS_LABEL: Record<ExpenseReportStatus, string> = {
  draft: "Draft",
  submitted: "Submitted",
  approved: "Approved",
  returned: "Returned",
};
const STATUS_COLOR: Record<ExpenseReportStatus, string> = {
  draft: "gray",
  submitted: "blue",
  approved: "green",
  returned: "orange",
};

export function ExpenseReportPage() {
  const { reportId } = useParams<{ reportId: string }>();
  const navigate = useNavigate();
  const reportQuery = useExpenseReport(reportId ?? "");
  const optionsQuery = useExpenseOptions();
  const approveReport = useApproveExpenseReport(reportId ?? "");
  const returnReport = useReturnExpenseReport(reportId ?? "");
  const deleteReport = useDeleteExpenseReport(reportId ?? "");

  const [isDirty, setIsDirty] = useState(false);
  const [confirmLeaveOpened, { open: openConfirmLeave, close: closeConfirmLeave }] =
    useDisclosure(false);
  const [returnOpened, { open: openReturn, close: closeReturn }] = useDisclosure(false);
  const [returnComment, setReturnComment] = useState("");
  const [deleteOpened, { open: openDelete, close: closeDelete }] = useDisclosure(false);
  const [ruleError, setRuleError] = useState<string | null>(null);

  function backToList() {
    if (isDirty) {
      openConfirmLeave();
      return;
    }
    navigate("/expenses");
  }

  if (reportQuery.isPending) return <Loader />;

  if (reportQuery.isError) {
    if (reportQuery.error instanceof ExpenseRuleError) {
      return (
        <Stack>
          <Title order={2}>Expense report not found</Title>
          <Anchor component={Link} to="/expenses">
            Back to expenses
          </Anchor>
        </Stack>
      );
    }
    return <Alert color="red">Could not load the expense report.</Alert>;
  }

  const report = reportQuery.data;
  const billingItems =
    optionsQuery.data?.find((option) => option.project.id === report.project.id)?.billing_items ?? [];

  async function handleApprove() {
    setRuleError(null);
    try {
      await approveReport.mutateAsync();
      notifications.show({ title: "Expense report approved", message: "" });
    } catch (error) {
      if (error instanceof ExpenseRuleError || error instanceof ExpenseConflictError) {
        setRuleError(error.message);
        return;
      }
      throw error;
    }
  }

  async function handleReturn() {
    setRuleError(null);
    try {
      await returnReport.mutateAsync(returnComment);
      setReturnComment("");
      closeReturn();
      notifications.show({ title: "Expense report returned", message: "" });
    } catch (error) {
      if (error instanceof ExpenseRuleError || error instanceof ExpenseConflictError) {
        setRuleError(error.message);
        return;
      }
      throw error;
    }
  }

  async function handleDelete() {
    await deleteReport.mutateAsync();
    closeDelete();
    notifications.show({ title: "Expense report deleted", message: "" });
    navigate("/expenses");
  }

  return (
    <Stack>
      <Anchor
        component="button"
        type="button"
        onClick={backToList}
        style={{ alignSelf: "flex-start" }}
      >
        ← Back to expenses
      </Anchor>

      <Group justify="space-between" align="flex-start" wrap="wrap">
        <div>
          <Group gap="sm">
            <Title order={2}>{report.project.name}</Title>
            <Badge color={STATUS_COLOR[report.status]}>{STATUS_LABEL[report.status]}</Badge>
          </Group>
          <Text c="dimmed">
            {report.project.customer.name} · {report.period_start} – {report.period_end} ·{" "}
            {report.user.name}
          </Text>
          {report.status !== "draft" && report.submitted_at && (
            <Text size="sm" c="dimmed">
              Submitted {new Date(report.submitted_at).toLocaleString()}
            </Text>
          )}
          {(report.status === "approved" || report.status === "returned") &&
            report.reviewed_at &&
            report.reviewed_by_name && (
              <Text size="sm" c="dimmed">
                {report.status === "approved" ? "Approved" : "Returned"} by{" "}
                {report.reviewed_by_name} · {new Date(report.reviewed_at).toLocaleString()}
              </Text>
            )}
        </div>
        <Group>
          {report.can_review && (
            <Group gap="xs">
              {report.status === "submitted" && (
                <Button size="xs" loading={approveReport.isPending} onClick={() => void handleApprove()}>
                  Approve
                </Button>
              )}
              <Button size="xs" variant="default" onClick={openReturn}>
                Return…
              </Button>
            </Group>
          )}
          {report.can_edit && report.status === "draft" && (
            <Button size="xs" variant="default" color="red" onClick={openDelete}>
              Delete
            </Button>
          )}
        </Group>
      </Group>

      {report.status === "returned" && report.return_comment && (
        <Alert color="orange" title="Returned for corrections">
          {report.return_comment}
        </Alert>
      )}

      {report.is_locked && (
        <Alert color="blue" variant="light" title="Sent to billing">
          This project's month has been sent to billing and can no longer be changed.
        </Alert>
      )}

      {ruleError && (
        <Alert color="red" onClose={() => setRuleError(null)} withCloseButton>
          {ruleError}
        </Alert>
      )}

      <ExpenseLinesTable report={report} billingItems={billingItems} onDirtyChange={setIsDirty} />

      <AttachmentsCard report={report} />

      <Modal opened={confirmLeaveOpened} onClose={closeConfirmLeave} title="Discard unsaved changes?">
        <Stack>
          <Text>You have unsaved changes on this report. Leaving now will discard them.</Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={closeConfirmLeave}>
              Cancel
            </Button>
            <Button
              color="red"
              onClick={() => {
                closeConfirmLeave();
                navigate("/expenses");
              }}
            >
              Discard and continue
            </Button>
          </Group>
        </Stack>
      </Modal>

      <Modal opened={returnOpened} onClose={closeReturn} title="Return this report for corrections">
        <Stack>
          <Textarea
            label="Comment"
            description="Tell the employee what needs to change"
            required
            autosize
            minRows={3}
            value={returnComment}
            onChange={(event) => setReturnComment(event.currentTarget.value)}
          />
          <Group justify="flex-end">
            <Button variant="default" onClick={closeReturn}>
              Cancel
            </Button>
            <Button
              color="orange"
              disabled={returnComment.trim() === ""}
              loading={returnReport.isPending}
              onClick={() => void handleReturn()}
            >
              Return
            </Button>
          </Group>
        </Stack>
      </Modal>

      <Modal opened={deleteOpened} onClose={closeDelete} title="Delete this draft report?">
        <Stack>
          <Text>This cannot be undone.</Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={closeDelete}>
              Cancel
            </Button>
            <Button color="red" loading={deleteReport.isPending} onClick={() => void handleDelete()}>
              Delete
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}
