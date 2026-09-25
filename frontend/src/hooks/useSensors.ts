import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { qk } from '@/lib/queryClient';
import * as sensorsApi from '@/api/sensors';

export const useSensorBatches = () =>
  useQuery({ queryKey: qk.sensorBatches, queryFn: sensorsApi.listBatches, refetchInterval: 30_000 });

export const useSensorBatch = (id?: number | string) =>
  useQuery({
    queryKey: qk.sensorBatch(id ?? ''),
    queryFn: () => sensorsApi.getBatch(id!),
    enabled: id != null,
  });

export function useSensorActions(batchId?: number | string) {
  const qc = useQueryClient();
  const update = (batch: sensorsApi.SensorBatch) => {
    qc.setQueryData(qk.sensorBatch(batch.id), batch);
    qc.invalidateQueries({ queryKey: qk.sensorBatches });
  };
  const confirm = useMutation({
    mutationFn: ({ links, observationCount }: { links: Record<string, number | null>; observationCount: number }) =>
      sensorsApi.confirmBatch(batchId!, links, observationCount),
    onSuccess: update,
  });
  const reject = useMutation({
    mutationFn: () => sensorsApi.rejectBatch(batchId!),
    onSuccess: update,
  });
  const discard = useMutation({
    mutationFn: () => sensorsApi.deleteBatch(batchId!),
    onSuccess: () => {
      qc.removeQueries({ queryKey: qk.sensorBatch(batchId!) });
      qc.invalidateQueries({ queryKey: qk.sensorBatches });
    },
  });
  return { confirm, reject, discard };
}
