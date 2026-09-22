import { api } from "@/api/client";
import { ApiError } from "@/api/errors";
import type { components } from "@/api/schema";

export type Customer = components["schemas"]["CustomerResponse"];
export type CustomerPage = components["schemas"]["CustomerPageResponse"];
export type BillingAddress = components["schemas"]["BillingAddressRequest"];
export type BillingPeriod = components["schemas"]["BillingPeriodRequest"];

export type InvoiceLocale = "sv" | "en";

export type CustomerCreateBody = {
  name: string;
  legal_name?: string | null;
  tax_id?: string | null;
  billing_email?: string | null;
  billing_address: BillingAddress;
  billing_period: BillingPeriod;
  currency: string;
  payment_terms_days: number;
  notes?: string | null;
  vat_rate?: number | null;
  vat_note?: string | null;
  invoice_locale?: InvoiceLocale | null;
  customer_number?: string | null;
  your_reference?: string | null;
};

export type CustomerUpdateBody = Partial<
  Omit<CustomerCreateBody, "billing_address" | "billing_period"> & {
    billing_address: BillingAddress | null;
    billing_period: BillingPeriod | null;
    is_active: boolean;
  }
>;

/** A customer with this name already exists (409). */
export class CustomerConflictError extends Error {
  constructor() {
    super("A customer with this name already exists");
    this.name = "CustomerConflictError";
  }
}

export class CustomerNotFoundError extends Error {
  constructor() {
    super("Customer not found");
    this.name = "CustomerNotFoundError";
  }
}

async function customerAwareError(response: Response): Promise<Error> {
  if (response.status === 409) return new CustomerConflictError();
  if (response.status === 404) return new CustomerNotFoundError();
  return new ApiError(response);
}

/** Active customers by default; pass `includeInactive` to also list archived ones. */
export async function listCustomers(params: {
  includeInactive?: boolean;
  limit?: number;
  offset?: number;
  search?: string;
}): Promise<CustomerPage> {
  const { data, response } = await api.GET("/api/v1/customers", {
    params: {
      query: {
        include_inactive: params.includeInactive,
        limit: params.limit,
        offset: params.offset,
        search: params.search,
      },
    },
  });
  if (!data) throw new ApiError(response);
  return data;
}

export async function getCustomer(customerId: string): Promise<Customer> {
  const { data, response } = await api.GET("/api/v1/customers/{customer_id}", {
    params: { path: { customer_id: customerId } },
  });
  if (!data) throw await customerAwareError(response);
  return data;
}

export async function createCustomer(body: CustomerCreateBody): Promise<Customer> {
  const { data, response } = await api.POST("/api/v1/customers", { body });
  if (!data) throw await customerAwareError(response);
  return data;
}

export async function updateCustomer(
  customerId: string,
  body: CustomerUpdateBody,
): Promise<Customer> {
  const { data, response } = await api.PATCH("/api/v1/customers/{customer_id}", {
    params: { path: { customer_id: customerId } },
    body,
  });
  if (!data) throw await customerAwareError(response);
  return data;
}
