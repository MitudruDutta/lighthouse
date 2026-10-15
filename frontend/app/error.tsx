"use client";

/** Whatever went wrong, the page says it plainly, and never shows the error itself. */
export default function Failed({ reset }: { reset: () => void }) {
  return (
    <div className="night grid min-h-screen place-items-center px-5">
      <div className="max-w-md text-center">
        <h1 className="display text-3xl">This page could not be shown just now</h1>
        <p className="mt-3 text-muted">
          Lighthouse may still be starting, or a part of it is busy. Try again in a few seconds.
        </p>
        <button type="button" onClick={reset} className="button mt-6">
          Try again
        </button>
      </div>
    </div>
  );
}
