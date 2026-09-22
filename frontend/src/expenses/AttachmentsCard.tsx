import {
  ActionIcon,
  Alert,
  Anchor,
  FileInput,
  Group,
  Select,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";

import {
  attachmentDownloadUrl,
  AttachmentTooLargeError,
  AttachmentTypeError,
  ExpenseConflictError,
  ExpenseRuleError,
  type ExpenseReport,
} from "@/expenses/api";
import {
  useAddExpenseAttachment,
  useDeleteExpenseAttachment,
  useSetExpenseAttachmentLine,
} from "@/expenses/hooks";
import { formatBytes } from "@/system/format";

type Props = {
  report: ExpenseReport;
};

export function AttachmentsCard({ report }: Props) {
  const addAttachment = useAddExpenseAttachment(report.id);
  const deleteAttachment = useDeleteExpenseAttachment(report.id);
  const setAttachmentLine = useSetExpenseAttachmentLine(report.id);
  const [uploadError, setUploadError] = useState<string | null>(null);

  // Labeled with the line's date too (not just its description) so the picker's value never
  // collides, in tests or in the DOM, with the line's own description text field above it.
  function lineLabel(line: (typeof report.lines)[number]): string {
    return `${line.expense_date} · ${line.description}`;
  }
  const lineOptions = report.lines.map((line) => ({ value: line.id, label: lineLabel(line) }));
  const lineNameById = new Map(report.lines.map((line) => [line.id, lineLabel(line)]));

  async function handleUpload(files: File[]) {
    setUploadError(null);
    for (const file of files) {
      try {
        await addAttachment.mutateAsync({ file });
      } catch (error) {
        if (
          error instanceof AttachmentTooLargeError ||
          error instanceof AttachmentTypeError ||
          error instanceof ExpenseRuleError ||
          error instanceof ExpenseConflictError
        ) {
          setUploadError(error.message);
          return;
        }
        throw error;
      }
    }
    notifications.show({ title: "Attachment(s) uploaded", message: "" });
  }

  async function handleDelete(attachmentId: string) {
    await deleteAttachment.mutateAsync(attachmentId);
    notifications.show({ title: "Attachment deleted", message: "" });
  }

  async function handleLineChange(attachmentId: string, lineId: string | null) {
    await setAttachmentLine.mutateAsync({ attachmentId, lineId });
  }

  return (
    <Stack>
      <Title order={4}>Attachments</Title>

      {uploadError && (
        <Alert color="red" onClose={() => setUploadError(null)} withCloseButton>
          {uploadError}
        </Alert>
      )}

      {report.attachments.length === 0 ? (
        <Text c="dimmed" size="sm">
          No receipts or invoices attached yet.
        </Text>
      ) : (
        <Table withTableBorder>
          <Table.Tbody>
            {report.attachments.map((attachment) => (
              <Table.Tr key={attachment.id}>
                <Table.Td>
                  <Anchor href={attachmentDownloadUrl(attachment.id)} download={attachment.file_name}>
                    {attachment.file_name}
                  </Anchor>
                </Table.Td>
                <Table.Td>
                  <Text size="sm" c="dimmed">
                    {formatBytes(attachment.size_bytes)}
                  </Text>
                </Table.Td>
                <Table.Td>
                  {report.can_edit ? (
                    <Select
                      aria-label={`Line for ${attachment.file_name}`}
                      placeholder="No line"
                      data={lineOptions}
                      value={attachment.line_id}
                      onChange={(value) => void handleLineChange(attachment.id, value)}
                      clearable
                      clearButtonProps={{ "aria-label": `Unlink ${attachment.file_name}` }}
                      w={200}
                    />
                  ) : (
                    <Text size="sm" c="dimmed">
                      {attachment.line_id ? lineNameById.get(attachment.line_id) : ""}
                    </Text>
                  )}
                </Table.Td>
                {report.can_edit && (
                  <Table.Td>
                    <ActionIcon
                      variant="subtle"
                      color="red"
                      aria-label={`Delete ${attachment.file_name}`}
                      loading={deleteAttachment.isPending}
                      onClick={() => void handleDelete(attachment.id)}
                    >
                      🗑
                    </ActionIcon>
                  </Table.Td>
                )}
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}

      {report.can_edit && (
        <Group>
          <FileInput
            aria-label="Upload receipts or invoices"
            placeholder="Choose file(s)…"
            multiple
            clearable
            value={[]}
            onChange={(files) => void handleUpload(files)}
            accept="application/pdf,image/jpeg,image/png,image/webp,image/heic"
            w={320}
            disabled={addAttachment.isPending}
          />
        </Group>
      )}
    </Stack>
  );
}
