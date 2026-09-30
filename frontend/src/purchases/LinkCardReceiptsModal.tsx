import {
  Alert,
  Button,
  Checkbox,
  Group,
  Loader,
  Modal,
  NumberInput,
  Stack,
  Table,
  Text,
} from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { useState } from "react";

import { addDays } from "@/timesheets/week";
import {
  PurchaseConflictError,
  PurchaseRuleError,
  type PurchaseDocument,
} from "@/purchases/api";
import { formatAmount } from "@/purchases/format";
import { useLinkCardReceipts, useUnlinkedCardReceipts } from "@/purchases/hooks";

/** Picks unlinked card receipts (by default those of the 62 days up to the card invoice date) and
 * links them with the base-currency amount from the card invoice's lines. */
export function LinkCardReceiptsModal({
  card,
  baseCurrency,
  opened,
  onClose,
}: {
  card: PurchaseDocument;
  baseCurrency: string;
  opened: boolean;
  onClose: () => void;
}) {
  const invoiceDate = card.document_date ?? "";
  const [dateFrom, setDateFrom] = useState(invoiceDate ? addDays(invoiceDate, -62) : "");
  const [dateTo, setDateTo] = useState(invoiceDate);
  const receipts = useUnlinkedCardReceipts(dateFrom, dateTo);
  const link = useLinkCardReceipts();
  // receipt id -> the typed base-currency amount; presence in the map means "selected".
  const [selected, setSelected] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  function toggle(receipt: PurchaseDocument, checked: boolean) {
    setSelected((previous) => {
      const next = { ...previous };
      if (checked) next[receipt.id] = "";
      else delete next[receipt.id];
      return next;
    });
  }

  const ids = Object.keys(selected);
  const ready = ids.length > 0 && ids.every((id) => Number(selected[id]) > 0);

  async function handleLink() {
    setError(null);
    try {
      await link.mutateAsync({
        cardInvoiceId: card.id,
        links: ids.map((id) => ({ receiptId: id, amountBase: selected[id] })),
      });
      onClose();
    } catch (linkError) {
      if (linkError instanceof PurchaseConflictError || linkError instanceof PurchaseRuleError) {
        setError(linkError.message);
        return;
      }
      throw linkError;
    }
  }

  return (
    <Modal opened={opened} onClose={onClose} title="Add receipts to this card invoice" size="xl">
      <Stack>
        <Group>
          <DateInput label="From" clearable value={dateFrom} onChange={(v) => setDateFrom(v ?? "")} />
          <DateInput label="To" clearable value={dateTo} onChange={(v) => setDateTo(v ?? "")} />
        </Group>
        {error && <Alert color="red">{error}</Alert>}
        {receipts.isLoading && <Loader />}
        {receipts.isSuccess && receipts.data.length === 0 && (
          <Text c="dimmed">No unlinked card receipts in this period.</Text>
        )}
        {receipts.data && receipts.data.length > 0 && (
          <Table>
            <Table.Thead>
              <Table.Tr>
                <Table.Th />
                <Table.Th>Date</Table.Th>
                <Table.Th>Vendor</Table.Th>
                <Table.Th ta="right">Amount</Table.Th>
                <Table.Th ta="right">{baseCurrency} on the invoice</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {receipts.data.map((receipt) => {
                const name = receipt.vendor || receipt.file_name;
                const isSelected = receipt.id in selected;
                return (
                  <Table.Tr key={receipt.id}>
                    <Table.Td>
                      <Checkbox
                        aria-label={`Select ${name}`}
                        checked={isSelected}
                        onChange={(event) => toggle(receipt, event.currentTarget.checked)}
                      />
                    </Table.Td>
                    <Table.Td>{receipt.document_date}</Table.Td>
                    <Table.Td>{name}</Table.Td>
                    <Table.Td ta="right">{formatAmount(receipt)}</Table.Td>
                    <Table.Td ta="right">
                      {isSelected && (
                        <NumberInput
                          aria-label={`${baseCurrency} amount of ${name}`}
                          decimalScale={2}
                          min={0}
                          value={selected[receipt.id] === "" ? "" : Number(selected[receipt.id])}
                          onChange={(value) =>
                            setSelected((previous) => ({
                              ...previous,
                              [receipt.id]: value === "" ? "" : String(value),
                            }))
                          }
                          w={130}
                          ml="auto"
                        />
                      )}
                    </Table.Td>
                  </Table.Tr>
                );
              })}
            </Table.Tbody>
          </Table>
        )}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button loading={link.isPending} disabled={!ready} onClick={() => void handleLink()}>
            Link {ids.length > 0 ? ids.length : ""} receipt{ids.length === 1 ? "" : "s"}
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
