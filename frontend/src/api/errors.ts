/** An API response with a status the caller does not handle. */
export class ApiError extends Error {
  readonly status: number;

  constructor(response: Response) {
    super(`API request failed with status ${response.status}`);
    this.name = "ApiError";
    this.status = response.status;
  }
}
