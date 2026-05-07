interface ErrorBannerProps {
  message: string;
  onDismiss: () => void;
}

export function ErrorBanner({ message, onDismiss }: ErrorBannerProps) {
  return (
    <div
      className="bg-red-50 border border-red-200 rounded-xl p-4 mb-6 flex items-start gap-3"
      role="alert"
      aria-live="assertive"
    >
      {/* Error icon */}
      <svg
        className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
        />
      </svg>

      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-red-800">Error</p>
        <p className="text-sm text-red-700 mt-0.5">{message}</p>
      </div>

      <button
        type="button"
        onClick={onDismiss}
        className="flex-shrink-0 text-sm font-medium text-red-700 hover:text-red-900 underline underline-offset-2 focus:outline-none focus:ring-2 focus:ring-red-500 rounded"
        aria-label="Try again"
      >
        Try again
      </button>
    </div>
  );
}
