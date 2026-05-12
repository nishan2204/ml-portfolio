import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import Navbar from '@/components/Navbar'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'Nishan Shetty - From Raw Data to Autonomous Action',
  description:
    'Data Scientist and AI Engineer with 8+ years building production ML and AI systems across scheduling optimization, forecasting, RAG agents, causal inference, and more.',
  openGraph: {
    title: 'Nishan Shetty - From Raw Data to Autonomous Action',
    description:
      'Data Scientist and AI Engineer with 8+ years building production ML and AI systems across scheduling optimization, forecasting, RAG agents, causal inference, and more.',
    url: 'https://nishanshetty.com',
    siteName: 'Nishan Shetty',
    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Nishan Shetty - From Raw Data to Autonomous Action',
    description:
      'Data Scientist and AI Engineer with 8+ years building production ML and AI systems across scheduling optimization, forecasting, RAG agents, causal inference, and more.',
  },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${inter.className} bg-black text-neutral-200 antialiased`}>
        <Navbar />
        {children}
      </body>
    </html>
  )
}
