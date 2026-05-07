import { useMutation, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { apiClient } from '../api/client';
import type { AnalyzeResponse, JobStatusResponse } from '../types/api';
import { TERMINAL_STATUSES } from '../types/api';

const POLL_INTERVAL_MS = 2000;
const MAX_POLL_DURATION_MS = 90_000;

export function useAnalysis() {
  const [jobId, setJobId] = useState<string | null>(null);
  const [pollStartedAt, setPollStartedAt] = useState<number | null>(null);

  const submitMutation = useMutation<AnalyzeResponse, Error, FormData>({
    mutationFn: (formData) => apiClient.submitAnalysis(formData),
    onSuccess: (data) => {
      setJobId(data.job_id);
      setPollStartedAt(Date.now());
    },
  });

  const statusQuery = useQuery<JobStatusResponse, Error>({
    queryKey: ['job-status', jobId],
    queryFn: () => apiClient.getJobStatus(jobId!),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (!status) return POLL_INTERVAL_MS;
      if (TERMINAL_STATUSES.includes(status)) return false;
      const elapsed = pollStartedAt ? Date.now() - pollStartedAt : 0;
      if (elapsed > MAX_POLL_DURATION_MS) return false;
      return POLL_INTERVAL_MS;
    },
  });

  const reset = () => {
    setJobId(null);
    setPollStartedAt(null);
  };

  return { submitMutation, statusQuery, jobId, reset };
}
