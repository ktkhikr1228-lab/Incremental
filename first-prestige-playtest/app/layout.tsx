import type { Metadata } from 'next';
import { Bebas_Neue, Noto_Sans_JP } from 'next/font/google';
import './globals.css';

const notoSans = Noto_Sans_JP({ variable: '--font-interface', subsets: ['latin'], weight: ['400', '600', '800'] });
const bebas = Bebas_Neue({ variable: '--font-display', subsets: ['latin'], weight: '400' });

export const metadata: Metadata = {
  title: '第一転生 | Manual Simulator',
  description: 'Wave 1から500までを体感できる第一転生シミュレーター',
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="ja"><body className={`${notoSans.variable} ${bebas.variable}`}>{children}</body></html>;
}
