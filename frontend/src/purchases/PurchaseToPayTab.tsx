import { Alert, Anchor, Badge, Button, Loader, Stack, Table, Text } from "@mantine/core";
import { useState } from "react";
import { Link } from "react-router";

import type { PurchaseDocument } from "@/purchases/api";
import { KIND_LABEL, formatAmount, formatBaseAmount } from "@/purchases/format";
import { MarkPaidModal } from "@/purchases/MarkPaidModal";
import { usePurchaseDocuments } from "@/purchases/hooks";
import { todayIso } from "@/timesheets/week";

/** Unpaid invoices and card invoices, earliest due date first, overdue ones highlighted, each with
 * a "Paid…" button. */
export function PurchaseToPayTab({ baseCurrency }: { baseCurrency: string }) {
  const unpaid = usePurchaseDocuments({
    stage: "registered",
    paymentStatus: "unpaid",
    sort: "due_date",
    limit: 200,
  });
  const [paying, setPaying] = useState<PurchaseDocument | null>(null);
  const today = todayIso();
  const items = unpaid.data?.items ?? [];

  return (
    <Stack>
      {unpaid.isLoading && <Loader />}
      {unpaid.isSuccess && items.length === 0 && <Text c="dimmed">Nothing to pay.</Text>}
      {(unpaid.data?.total ?? 0) > items.length && (
        <Alert color="yellow">Showing the {items.length} earliest due of {unpaid.data?.total}.</Alert>
      )}
      {items.length > 0 && (
        <Table withTableBorder>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Due</Table.Th>
              <Table.Th>Kind</Table.Th>
              <Table.Th>Vendor</Table.Th>
              <Table.Th>No.</Table.Th>
              <Table.Th ta="right">Amount</Table.Th>
              <Table.Th ta="right">{baseCurrency}</Table.Th>
              <Table.Th />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {items.map((document) => {
              const overdue = document.due_date !== null && document.due_date < today;
              return (
                <Table.Tr key={document.id}>
                  <Table.Td c={overdue ? "red" : undefined} fw={overdue ? 600 : undefined}>
                    {document.due_date ?? "—"}
                    {overdue && (
                      <Badge ml="xs" size="xs" color="red">
                        Overdue
                      </Badge>
                    )}
                  </Table.Td>
                  <Table.Td>{KIND_LABEL[document.kind ?? "other"]}</Table.Td>
                  <Table.Td>
                    <Anchor component={Link} to={`/purchases/${document.id}`}>
                      {document.vendor || document.file_name}
                    </Anchor>
                  </Table.Td>
                  <Table.Td>{document.document_no}</Table.Td>
                  <Table.Td ta="right">{formatAmount(document)}</Table.Td>
                  <Table.Td ta="right">{formatBaseAmount(document, baseCurrency)}</Table.Td>
                  <Table.Td ta="right">
                    <Button size="xs" variant="default" onClick={() => setPaying(document)}>
                      Paid…
                    </Button>
                  </Table.Td>
                </Table.Tr>
              );
            })}
          </Table.Tbody>
        </Table>
      )}
      <Text size="xs" c="dimmed">
        ~ marks an estimate at the document date's rate; it becomes final when the document is paid.
      </Text>
      <MarkPaidModal
        key={paying?.id ?? "none"}
        document={paying}
        baseCurrency={baseCurrency}
        onClose={() => setPaying(null)}
      />
    </Stack>
  );
}
