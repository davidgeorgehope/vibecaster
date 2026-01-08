/**
 * Fetch wrapper with automatic retry on network errors (including QUIC protocol errors).
 * Uses exponential backoff with jitter to prevent thundering herd.
 */

interface RetryOptions {
  maxRetries?: number;
  baseDelay?: number;
  maxDelay?: number;
  retryOn?: (error: Error, response?: Response) => boolean;
}

const DEFAULT_OPTIONS: Required<RetryOptions> = {
  maxRetries: 3,
  baseDelay: 1000,
  maxDelay: 10000,
  retryOn: (error: Error, response?: Response) => {
    // Retry on network errors (TypeError is thrown by fetch on network failure)
    if (error instanceof TypeError) return true;

    // Retry on specific error messages that indicate QUIC/connection issues
    const errorMessage = error.message?.toLowerCase() || '';
    const quicPatterns = [
      'quic',
      'protocol_error',
      'connection',
      'network',
      'failed to fetch',
      'load failed',
      'networkerror',
    ];
    if (quicPatterns.some(pattern => errorMessage.includes(pattern))) return true;

    // Retry on 502, 503, 504 (gateway/service errors)
    if (response && [502, 503, 504].includes(response.status)) return true;

    return false;
  },
};

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function calculateDelay(attempt: number, baseDelay: number, maxDelay: number): number {
  // Exponential backoff: 1s, 2s, 4s, 8s...
  const exponentialDelay = baseDelay * Math.pow(2, attempt);
  // Add jitter (random 0-500ms) to prevent synchronized retries
  const jitter = Math.random() * 500;
  // Cap at maxDelay
  return Math.min(exponentialDelay + jitter, maxDelay);
}

export async function fetchWithRetry(
  input: RequestInfo | URL,
  init?: RequestInit,
  options?: RetryOptions
): Promise<Response> {
  const opts = { ...DEFAULT_OPTIONS, ...options };
  let lastError: Error | null = null;
  let lastResponse: Response | undefined;

  for (let attempt = 0; attempt <= opts.maxRetries; attempt++) {
    try {
      const response = await fetch(input, init);
      lastResponse = response;

      // Check if we should retry based on response status
      if (!response.ok && opts.retryOn(new Error(`HTTP ${response.status}`), response)) {
        if (attempt < opts.maxRetries) {
          const delay = calculateDelay(attempt, opts.baseDelay, opts.maxDelay);
          console.warn(`[fetchWithRetry] HTTP ${response.status}, retrying in ${Math.round(delay)}ms (attempt ${attempt + 1}/${opts.maxRetries})`);
          await sleep(delay);
          continue;
        }
      }

      return response;
    } catch (error) {
      lastError = error instanceof Error ? error : new Error(String(error));

      // Check if we should retry
      if (opts.retryOn(lastError, lastResponse) && attempt < opts.maxRetries) {
        const delay = calculateDelay(attempt, opts.baseDelay, opts.maxDelay);
        console.warn(`[fetchWithRetry] Network error: ${lastError.message}, retrying in ${Math.round(delay)}ms (attempt ${attempt + 1}/${opts.maxRetries})`);
        await sleep(delay);
        continue;
      }

      throw lastError;
    }
  }

  // Should never reach here, but TypeScript needs this
  throw lastError || new Error('Max retries exceeded');
}

/**
 * Helper to create a fetch function with retry that preserves the same signature.
 * Useful for replacing fetch calls with minimal code changes.
 */
export function createRetryFetch(defaultOptions?: RetryOptions) {
  return (input: RequestInfo | URL, init?: RequestInit) =>
    fetchWithRetry(input, init, defaultOptions);
}

/**
 * Retry wrapper for existing fetch promises.
 * Use this to wrap fetch calls in SSE/streaming scenarios where you need
 * to retry the entire operation.
 */
export async function withRetry<T>(
  operation: () => Promise<T>,
  options?: RetryOptions
): Promise<T> {
  const opts = { ...DEFAULT_OPTIONS, ...options };
  let lastError: Error | null = null;

  for (let attempt = 0; attempt <= opts.maxRetries; attempt++) {
    try {
      return await operation();
    } catch (error) {
      lastError = error instanceof Error ? error : new Error(String(error));

      if (opts.retryOn(lastError) && attempt < opts.maxRetries) {
        const delay = calculateDelay(attempt, opts.baseDelay, opts.maxDelay);
        console.warn(`[withRetry] Error: ${lastError.message}, retrying in ${Math.round(delay)}ms (attempt ${attempt + 1}/${opts.maxRetries})`);
        await sleep(delay);
        continue;
      }

      throw lastError;
    }
  }

  throw lastError || new Error('Max retries exceeded');
}
