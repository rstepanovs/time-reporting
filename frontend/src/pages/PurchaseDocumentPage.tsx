import {
  Alert,
  Anchor,
  Badge,
  Button,
  Grid,
  Group,
  Loader,
  Modal,
  Paper,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import {
  PurchaseConflictError,
  PurchaseRuleError,
  purchaseFileUrl,
  type PurchaseDocument,
} from "@/purchases/api";
import {
  KIND_LABEL,
  METHOD_LABEL,
  formatAmount,
  formatBaseAmount,
  paymentStatusText,
} from "@/purchases/format";
import {
  usePurchaseDocument,
  usePurchasesSummary,
  useMarkPurchaseUnpaid,
  useReturnPurchaseToInbox,
} from "@/purchases/hooks";
import { MarkPaidModal } from "@/purchases/MarkPaidModal";
import { PurchaseRegisterForm } from "@/purchases/PurchaseRegisterForm";

function Preview({ document }: { document: PurchaseDocument }) {
  const url = purchaseFileUrl(document.id);
  if (document.content_type === "application/pdf") {
    return (
      <iframe title="Document preview" src={url} style={{ width: "100%", height: 600, border: 0 }} />
    );
  }
  if (document.content_type === "image/heic") {
    return (
      <Text size="sm">
        This image can't be previewed in the browser. <Anchor href={url}>Open the file</Anchor>
      </Text>
    );
  }
  return <img alt="Document preview" src={url} style={{ maxWidth: "100%", maxHeight: 600 }} />;
}

/** `/purchases/:documentId` — one registered document: its file, an editable form, and the
 * Paid/Unpaid and "Back to inbox" actions. */
export function PurchaseDocumentPage() {
  const { documentId = "" } = useParams();
  const navigate = useNavigate();
  const document = usePurchaseDocument(documentId);
  const summary = usePurchasesSummary();
  const markUnpaid = useMarkPurchaseUnpaid();
  const returnToInbox = useReturnPurchaseToInbox();
  const [paying, setPaying] = useState(false);
  const [confirmOpened, { open: openConfirm, close: closeConfirm }] = useDisclosure();
  const [error, setError] = useState<string | null>(null);

  if (document.isLoading || summary.isLoading) return <Loader />;
  if (document.isError || !document.data || !summary.data) {
    return <Alert color="red">This document could not be loaded.</Alert>;
  }
  const doc = document.data;
  const baseCurrency = summary.data.base_currency;
  const isPayable = doc.kind === "invoice" || doc.kind === "card_invoice";
  const rebilled = doc.rebilled_expense_line_id !== null;

  async function run(action: () => Promise<unknown>, after?: () => void) {
    setError(null);
    try {
      await action();
      after?.();
    } catch (actionError) {
      if (actionError instanceof PurchaseConflictError || actionError instanceof PurchaseRuleError) {
        setError(actionError.message);
        return;
      }
      throw actionError;
    }
  }

  return (
    <Stack>
      <Anchor component={Link} to="/purchases?tab=register" style={{ alignSelf: "flex-start" }}>
        ← Back to purchases
      </Anchor>

      <Group justify="space-between" align="flex-start">
        <div>
          <Group gap="sm">
            <Title order={2}>{doc.vendor || doc.file_name}</Title>
            {doc.kind && <Badge variant="light">{KIND_LABEL[doc.kind]}</Badge>}
            {doc.stage === "discarded" && <Badge color="gray">Discarded</Badge>}
            {rebilled && <Badge color="teal">Rebilled</Badge>}
          </Group>
          <Text c="dimmed" size="sm">
            {[doc.document_no, doc.document_date, paymentStatusText(doc)]
              .filter(Boolean)
              .join(" · ")}
          </Text>
          {doc.amount !== null && (
            <Text size="sm">
              {formatAmount(doc)} · {formatBaseAmount(doc, baseCurrency)}
              {doc.rate_source === "manual" && " (set by hand)"}
              {doc.rate_source === "card_invoice" && " (from the card invoice)"}
              {doc.exchange_rate && doc.rate_source === "riksbank" && doc.rate_date
                ? ` · rate ${doc.exchange_rate} of ${doc.rate_date}`
                : ""}
            </Text>
          )}
          {doc.payment_method && doc.payment_status === "paid" && (
            <Text size="sm" c="dimmed">
              {METHOD_LABEL[doc.payment_method]}
            </Text>
          )}
        </div>
        <Group>
          <Anchor href={purchaseFileUrl(doc.id)} download>
            Download
          </Anchor>
          {doc.stage === "registered" && isPayable && doc.payment_status === "unpaid" && (
            <Button size="xs" onClick={() => setPaying(true)}>
              Paid…
            </Button>
          )}
          {doc.stage === "registered" && isPayable && doc.payment_status === "paid" && (
            <Button
              size="xs"
              variant="default"
              loading={markUnpaid.isPending}
              onClick={() => void run(() => markUnpaid.mutateAsync(doc.id))}
            >
              Mark unpaid
            </Button>
          )}
          {doc.stage === "registered" && !rebilled && (
            <Button size="xs" variant="default" color="red" onClick={openConfirm}>
              Back to inbox…
            </Button>
          )}
        </Group>
      </Group>

      {error && (
        <Alert color="red" withCloseButton onClose={() => setError(null)}>
          {error}
        </Alert>
      )}
      {doc.stage === "inbox" && (
        <Alert color="blue">
          This document is still in the inbox. <Anchor component={Link} to="/purchases">Register it there.</Anchor>
        </Alert>
      )}
      {rebilled && (
        <Alert color="teal">
          This document has been rebilled to a project, so it can no longer be edited.
        </Alert>
      )}

      <Grid>
        <Grid.Col span={{ base: 12, lg: 6 }}>
          <Paper withBorder p="xs">
            <Preview document={doc} />
          </Paper>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 6 }}>
          {doc.stage === "registered" && !rebilled && (
            <PurchaseRegisterForm
              key={`${doc.id}-${doc.updated_at}`}
              document={doc}
              baseCurrency={baseCurrency}
              mode="edit"
            />
          )}
        </Grid.Col>
      </Grid>

      <MarkPaidModal
        key={`${doc.id}-${paying}`}
        document={paying ? doc : null}
        baseCurrency={baseCurrency}
        onClose={() => setPaying(false)}
      />

      <Modal opened={confirmOpened} onClose={closeConfirm} title="Send back to the inbox?">
        <Stack>
          <Text>
            The classification, amounts and payment details are cleared; the file stays. A card
            invoice with receipts linked to it can't be sent back.
          </Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={closeConfirm}>
              Cancel
            </Button>
            <Button
              color="red"
              loading={returnToInbox.isPending}
              onClick={() => {
                closeConfirm();
                void run(
                  () => returnToInbox.mutateAsync(doc.id),
                  () => {
                    notifications.show({ title: "Back in the inbox", message: doc.file_name });
                    navigate("/purchases");
                  },
                );
              }}
            >
              Send back
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}
