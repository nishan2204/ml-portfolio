import type { MetadataRoute } from 'next'
import { projects } from '@/lib/projects'

const BASE_URL = 'https://nishanshetty.com'

export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date()

  const staticEntries: MetadataRoute.Sitemap = [
    {
      url: BASE_URL,
      lastModified: now,
      changeFrequency: 'weekly',
      priority: 1.0,
    },
    {
      url: `${BASE_URL}/#about`,
      lastModified: now,
      changeFrequency: 'monthly',
      priority: 0.9,
    },
    {
      url: `${BASE_URL}/#contact`,
      lastModified: now,
      changeFrequency: 'monthly',
      priority: 0.6,
    },
    {
      url: `${BASE_URL}/resume.pdf`,
      lastModified: now,
      changeFrequency: 'monthly',
      priority: 0.7,
    },
  ]

  const projectEntries: MetadataRoute.Sitemap = projects
    .sort((a, b) => a.id - b.id)
    .map((p) => ({
      url: `${BASE_URL}/#project-${p.id}`,
      lastModified: now,
      changeFrequency: 'monthly' as const,
      priority: 0.8,
    }))

  return [...staticEntries, ...projectEntries]
}
