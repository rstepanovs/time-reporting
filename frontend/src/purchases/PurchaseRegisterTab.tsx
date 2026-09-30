import {
  Anchor,
  Badge,
  Group,
  Loader,
  Pagination,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
} from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { useDebouncedValue } from "@mantine/hooks";
import { useState } from "react";
import { Link } from "react-router";

import type { PaymentStatus, PurchaseKind } from "@/purchases/api";
import {
  KIND_LABEL,
  formatAmount,
  formatBaseAmount,
  paymentStatusText,
} from "@/purchases/format";
import { usePurchaseDocuments } from "@/purchases/hooks";

const PAGE_SIZE = 20;

const KIND_OPTIONS = (Object.keys(KIND_LABEL) as PurchaseKind[]).map((value) => ({
  value,
  label: KIND_LABEL[value],
}));
const STATUS_OPTIONS: { value: PaymentStatus; label: string }[] = [
  { value: "unpaid", label: "Unpaid" },
  { value: "paid", label: "Paid" },
];

/** Every registered document: filterable by kind, payment state, date range and a text search
 * (vendor, number, description), newest document date first, paginated. */
export function PurchaseRegisterTab({ baseCurrency }: { baseCurrency: string }) {
  const [kind, setKind] = useState<PurchaseKind | null>(null);
  const [paymentStatus, setPaymentStatus] = useState<PaymentStatus | null>(null);
  const [search, setSearch] = useState("");
  const [debouncedSearch] = useDebouncedValue(search, 300);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [page, setPage] = useState(1);

  const documents = usePurchaseDocuments({
    stage: "registered",
    kind: kind ?? undefined,
    paymentStatus: paymentStatus ?? undefined,
    search: debouncedSearch,
    dateFrom,
    dateTo,
    sort: "document_date",
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  });

  // Any filter change starts over from the first page.
  function filter<T>(setter: (value: T) => void) {
    return (value: T) => {
      setter(value);
      setPage(1);
    };
  }

  const items = documents.data?.items ?? [];
  const totalPages = Math.max(1, Math.ceil((documents.data?.total ?? 0) / PAGE_SIZE));

  return (
    <Stack>
      <Group align="flex-end">
        <Select
          label="Kind"
          placeholder="All"
          clearable
          data={KIND_OPTIONS}
          value={kind}
          onChange={filter((value: string | null) => setKind(value as PurchaseKind | null))}
          w={150}
        />
        <Select
          label="Payment"
          placeholder="All"
          clearable
          data={STATUS_OPTIONS}
          value={paymentStatus}
          onChange={filter((value: string | null) =>
            setPaymentStatus(value as PaymentStatus | null),
          )}
          w={130}
        />
        <DateInput
          label="From"
          clearable
          value={dateFrom}
          onChange={filter((value: string | null) => setDateFrom(value ?? ""))}
          w={150}
        />
        <DateInput
          label="To"
          clearable
          value={dateTo}
          onChange={filter((value: string | null) => setDateTo(value ?? ""))}
          w={150}
        />
        <TextInput
          label="Search"
          placeholder="Vendor, number, description"
          value={search}
          onChange={(event) => {
            setSearch(event.currentTarget.value);
            setPage(1);
          }}
          w={240}
        />
      </Group>

      {documents.isLoading && <Loader />}
      {documents.isSuccess && items.length === 0 && (
        <Text c="dimmed">No documents match.</Text>
      )}
      {items.length > 0 && (
        <Table withTableBorder>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Date</Table.Th>
              <Table.Th>Kind</Table.Th>
              <Table.Th>Vendor</Table.Th>
              <Table.Th>No.</Table.Th>
              <Table.Th ta="right">Amount</Table.Th>
              <Table.Th ta="right">{baseCurrency}</Table.Th>
              <Table.Th>Status</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {items.map((document) => (
              <Table.Tr key={document.id}>
                <Table.Td>{document.document_date}</Table.Td>
                <Table.Td>{KIND_LABEL[document.kind ?? "other"]}</Table.Td>
                <Table.Td>
                  <Anchor component={Link} to={`/purchases/${document.id}`}>
                    {document.vendor || document.file_name}
                  </Anchor>
                </Table.Td>
                <Table.Td>{document.document_no}</Table.Td>
                <Table.Td ta="right">{formatAmount(document)}</Table.Td>
                <Table.Td ta="right">{formatBaseAmount(document, baseCurrency)}</Table.Td>
                <Table.Td>
                  {paymentStatusText(document)}
                  {document.rebilled_expense_line_id && (
                    <Badge ml="xs" size="xs" variant="light">
                      Rebilled
                    </Badge>
                  )}
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
      {totalPages > 1 && <Pagination total={totalPages} value={page} onChange={setPage} />}
    </Stack>
  );
}
