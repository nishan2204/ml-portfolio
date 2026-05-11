import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import Navbar from '@/components/Navbar'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'DS Portfolio: ML Systems That Work in the Real World',
  description:
    'Data Science Manager with 7+ years building production ML systems that are accurate, explainable, and fast enough to matter.',
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
