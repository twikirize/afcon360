import { MobileAuthError } from "@afcon360/mobile-core";

export function serviceErrorMessage(error: unknown, service: string): string {
  if (error instanceof MobileAuthError && error.status === 404 && error.code === "api_error") {
    return `The ${service} service is not enabled in this AFCON360 backend release yet. The screen is available in the app, but the backend connection must be deployed before this service can be used.`;
  }
  if (error instanceof MobileAuthError && error.status === 503 && error.code === "api_error") {
    return `${service} is temporarily unavailable. Please try again later.`;
  }
  if (error instanceof Error) return error.message;
  return `AFCON360 could not complete the ${service.toLowerCase()} request. Please try again.`;
}
