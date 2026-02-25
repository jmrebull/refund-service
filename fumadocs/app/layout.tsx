import type { ReactNode } from 'react';
import { RootProvider } from 'fumadocs-ui/provider/next';
import './global.css';

export const metadata = {
  title: {
    template: '%s — Solara Refund API',
    default: 'Solara Retail — Refund API',
  },
  description:
    'Issue and track refunds across full, split, partial, installment, and cross-border payment scenarios.',
};

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
        <RootProvider>{children}</RootProvider>
      </body>
    </html>
  );
}
