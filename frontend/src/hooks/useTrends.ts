import { useEffect, useState } from 'react'
import { api } from '../services/api'

export function useTrends(platform: string, metricNames: string[]) {
  const [data, setData] = useState<Record<string, number | string | null>[]>([])

  useEffect(() => {
    if (!metricNames.length) return
    api
      .trends({ platform, metric_names: metricNames.join(',') })
      .then(setData)
      .catch(() => {})
  }, [platform, metricNames.join(',')])

  return data
}
