import { Alert, Anchor, Button, Group, NumberInput, Stack, Table, Text, Title } from "@mantine/core";
import { useState } from "react";
import { Link } from "react-router";

import {
  PurchaseConflictError,
  PurchaseRuleError,
  type PurchaseDocument,
} from "@/purchases/api";
import { formatAmount } from "@/purchases/format";
import {
  useCardInvoice,
  useUnlinkCardReceipt,
  useUpdateCardReceiptAmount,
} from "@/purchases/hooks";
import { LinkCardReceiptsModal } from "@/purchases/LinkCardReceiptsModal";

function money(value: string, currency: string): string {
  const formatted = Number(value).toLocaleString("sv-SE", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return `${formatted} ${currency}`;
}

/** One linked receipt: its own amount, the base-currency amount as typed from the card invoice
 * line (saved explicitly), and Unlink. */
function ReceiptRow({
  receipt,
  baseCurrency,
  onError,
}: {
  receipt: PurchaseDocument;
  baseCurrency: string;
  onError: (message: string) => void;
}) {
  const update = useUpdateCardReceiptAmount();
  const unlink = useUnlinkCardReceipt();
  const saved = receipt.amount_base ?? "";
  const [amount, setAmount] = useState(saved);

  async function run(action: () => Promise<unknown>) {
    try {
      await action();
    } catch (error) {
      if (error instanceof PurchaseConflictError || error instanceof PurchaseRuleError) {
        onError(error.message);
        return;
      }
      throw error;
    }
  }

  const changed = amount !== "" && Number(amount) !== Number(saved);

  return (
    <Table.Tr>
      <Table.Td>{receipt.document_date}</Table.Td>
      <Table.Td>
        <Anchor component={Link} to={`/purchases/${receipt.id}`}>
          {receipt.vendor || receipt.file_name}
        </Anchor>
      </Table.Td>
      <Table.Td ta="right">{formatAmount(receipt)}</Table.Td>
      <Table.Td>
        <Group gap="xs" justify="flex-end" wrap="nowrap">
          <NumberInput
            aria-label={`${baseCurrency} amount of ${receipt.vendor || receipt.file_name}`}
            decimalScale={2}
            min={0}
            value={amount === "" ? "" : Number(amount)}
            onChange={(value) => setAmount(value === "" ? "" : String(value))}
            w={130}
          />
          <Button
            size="xs"
            variant="default"
            disabled={!changed}
            loading={update.isPending}
            aria-label={`Save amount of ${receipt.vendor || receipt.file_name}`}
            onClick={() =>
              void run(() => update.mutateAsync({ receiptId: receipt.id, amountBase: amount }))
            }
          >
            Save
          </Button>
        </Group>
      </Table.Td>
      <Table.Td ta="right">
        <Button
          size="xs"
          variant="subtle"
          color="red"
          loading={unlink.isPending}
          aria-label={`Unlink ${receipt.vendor || receipt.file_name}`}
          onClick={() => void run(() => unlink.mutateAsync(receipt.id))}
        >
          Unlink
        </Button>
      </Table.Td>
    </Table.Tr>
  );
}

/** A card invoice's receipts: each receipt's base-currency amount is typed from the invoice's
 * lines; the sum is compared with the invoice's own total, and the difference (fees, interest,
 * purchases with no receipt yet) is shown. */
export function CardInvoiceSection({
  card,
  baseCurrency,
}: {
  card: PurchaseDocument;
  baseCurrency: string;
}) {
  const cardInvoice = useCardInvoice(card.id, true);
  const [linking, setLinking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!cardInvoice.data) return null;
  const { receipts, receipts_total_base: total, difference_base: difference } = cardInvoice.data;

  return (
    <Stack gap="xs">
      <Group justify="space-between">
        <Title order={4}>Receipts on this card invoice</Title>
        <Button size="xs" onClick={() => setLinking(true)}>
          Add receipts…
        </Button>
      </Group>
      {error && (
        <Alert color="red" withCloseButton onClose={() => setError(null)}>
          {error}
        </Alert>
      )}
      {receipts.length === 0 ? (
        <Text c="dimmed" size="sm">
          No receipts linked yet.
        </Text>
      ) : (
        <Table withTableBorder>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Date</Table.Th>
              <Table.Th>Vendor</Table.Th>
              <Table.Th ta="right">Amount</Table.Th>
              <Table.Th ta="right">{baseCurrency} on the invoice</Table.Th>
              <Table.Th />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {receipts.map((receipt) => (
              <ReceiptRow
                key={`${receipt.id}-${receipt.updated_at}`}
                receipt={receipt}
                baseCurrency={baseCurrency}
                onError={setError}
              />
            ))}
          </Table.Tbody>
        </Table>
      )}
      <Stack gap={2} aria-label="Card invoice totals">
        <Text size="sm">Receipts total: {money(total, baseCurrency)}</Text>
        <Text size="sm">
          Card invoice total:{" "}
          {card.amount_base ? money(card.amount_base, baseCurrency) : "not known yet"}
        </Text>
        {difference !== null && (
          <Text size="sm" fw={600} c={Number(difference) === 0 ? "green" : "orange"}>
            Difference: {money(difference, baseCurrency)}
            {Number(difference) !== 0 && " — fees, interest or purchases without a receipt"}
          </Text>
        )}
      </Stack>
      <LinkCardReceiptsModal
        key={`${card.id}-${linking}`}
        card={card}
        baseCurrency={baseCurrency}
        opened={linking}
        onClose={() => {
          setLinking(false);
        }}
      />
    </Stack>
  );
}
