import {
  Alert,
  Anchor,
  Badge,
  Button,
  FileInput,
  Grid,
  Group,
  Loader,
  Paper,
  Stack,
  Table,
  Tabs,
  Text,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";
import { useSearchParams } from "react-router";

import {
  PurchaseConflictError,
  PurchaseFileTooLargeError,
  PurchaseFileTypeError,
  PurchaseRuleError,
  purchaseFileUrl,
  type PurchaseDocument,
} from "@/purchases/api";
import {
  useDiscardPurchaseDocument,
  usePurchaseDocuments,
  usePurchasesSummary,
  useUploadPurchaseDocuments,
} from "@/purchases/hooks";
import { PurchaseRegisterForm } from "@/purchases/PurchaseRegisterForm";
import { formatBytes } from "@/system/format";

const ACCEPT = "application/pdf,image/jpeg,image/png,image/webp,image/heic";

function sourceLabel(document: PurchaseDocument): string {
  if (document.source === "email") {
    return document.email_subject || document.email_from || "Email";
  }
  return "Uploaded";
}

function Preview({ document }: { document: PurchaseDocument }) {
  const url = purchaseFileUrl(document.id);
  if (document.content_type === "application/pdf") {
    return <iframe title="Document preview" src={url} style={{ width: "100%", height: 560, border: 0 }} />;
  }
  if (document.content_type === "image/heic") {
    // Most browsers can't render HEIC inline.
    return (
      <Text size="sm">
        This image can't be previewed in the browser. <Anchor href={url}>Open the file</Anchor>
      </Text>
    );
  }
  return <img alt="Document preview" src={url} style={{ maxWidth: "100%", maxHeight: 560 }} />;
}

function InboxTab() {
  const inbox = usePurchaseDocuments("inbox");
  const summary = usePurchasesSummary();
  const upload = useUploadPurchaseDocuments();
  const discard = useDiscardPurchaseDocument();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const documents = inbox.data ?? [];
  const selected = documents.find((document) => document.id === selectedId) ?? documents[0] ?? null;

  async function handleUpload(files: File[]) {
    if (files.length === 0) return;
    setError(null);
    try {
      const created = await upload.mutateAsync(files);
      setSelectedId(created[0]?.id ?? null);
    } catch (uploadError) {
      if (
        uploadError instanceof PurchaseFileTooLargeError ||
        uploadError instanceof PurchaseFileTypeError
      ) {
        setError(uploadError.message);
        return;
      }
      throw uploadError;
    }
  }

  async function handleDiscard(document: PurchaseDocument) {
    setError(null);
    try {
      await discard.mutateAsync(document.id);
      notifications.show({ title: "Document discarded", message: document.file_name });
    } catch (discardError) {
      if (discardError instanceof PurchaseConflictError || discardError instanceof PurchaseRuleError) {
        setError(discardError.message);
        return;
      }
      throw discardError;
    }
  }

  return (
    <Stack>
      <FileInput
        aria-label="Upload documents"
        placeholder="Upload scans, photos or PDFs…"
        accept={ACCEPT}
        multiple
        value={[]}
        onChange={(files) => void handleUpload(files)}
        disabled={upload.isPending}
        w={360}
      />
      {error && (
        <Alert color="red" withCloseButton onClose={() => setError(null)}>
          {error}
        </Alert>
      )}
      {inbox.isLoading && <Loader />}
      {inbox.isSuccess && documents.length === 0 && (
        <Text c="dimmed">The inbox is empty. Scanned or emailed documents will appear here.</Text>
      )}
      {selected && (
        <Grid>
          <Grid.Col span={{ base: 12, md: 4 }}>
            <Table highlightOnHover withTableBorder>
              <Table.Tbody>
                {documents.map((document) => (
                  <Table.Tr
                    key={document.id}
                    onClick={() => setSelectedId(document.id)}
                    bg={document.id === selected.id ? "var(--mantine-color-blue-light)" : undefined}
                    style={{ cursor: "pointer" }}
                  >
                    <Table.Td>
                      <Text size="sm" fw={500}>
                        {document.file_name}
                      </Text>
                      <Text size="xs" c="dimmed">
                        {sourceLabel(document)} · {formatBytes(document.size_bytes)} ·{" "}
                        {new Date(document.created_at).toLocaleDateString()}
                      </Text>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Grid.Col>
          <Grid.Col span={{ base: 12, md: 8 }}>
            <Stack>
              <Group justify="space-between">
                <Title order={4}>{selected.file_name}</Title>
                <Group gap="xs">
                  <Anchor href={purchaseFileUrl(selected.id)} size="sm" download>
                    Download
                  </Anchor>
                  <Button
                    variant="default"
                    color="red"
                    size="xs"
                    loading={discard.isPending}
                    onClick={() => void handleDiscard(selected)}
                  >
                    Discard
                  </Button>
                </Group>
              </Group>
              <Grid>
                <Grid.Col span={{ base: 12, lg: 6 }}>
                  <Paper withBorder p="xs">
                    <Preview document={selected} />
                  </Paper>
                </Grid.Col>
                <Grid.Col span={{ base: 12, lg: 6 }}>
                  {summary.data ? (
                    <PurchaseRegisterForm
                      key={selected.id}
                      document={selected}
                      baseCurrency={summary.data.base_currency}
                    />
                  ) : (
                    <Loader />
                  )}
                </Grid.Col>
              </Grid>
            </Stack>
          </Grid.Col>
        </Grid>
      )}
    </Stack>
  );
}

const TABS = ["inbox"] as const;
type Tab = (typeof TABS)[number];

export function PurchasesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const requested = searchParams.get("tab");
  const tab: Tab = TABS.find((candidate) => candidate === requested) ?? "inbox";
  const summary = usePurchasesSummary();

  return (
    <Stack>
      <Title order={2}>Purchases</Title>
      <Tabs value={tab} onChange={(value) => value && setSearchParams({ tab: value })}>
        <Tabs.List>
          <Tabs.Tab value="inbox">
            <Group gap="xs">
              Inbox
              {summary.data && summary.data.inbox_count > 0 && (
                <Badge size="sm" circle>
                  {summary.data.inbox_count}
                </Badge>
              )}
            </Group>
          </Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="inbox" pt="md">
          <InboxTab />
        </Tabs.Panel>
      </Tabs>
    </Stack>
  );
}
