import { t } from '@lingui/core/macro';
import {
  Alert,
  Anchor,
  Button,
  Divider,
  FileInput,
  Group,
  List,
  Modal,
  Stack,
  Switch,
  Text
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import {
  IconCircleCheck,
  IconDownload,
  IconExclamationCircle,
  IconFileUpload
} from '@tabler/icons-react';
import { useState } from 'react';

import { ApiEndpoints } from '@lib/enums/ApiEndpoints';
import { apiUrl } from '@lib/functions/Api';
import { api } from '../../../App';

const TEMPLATE_CONTENT =
  '\ufeff子件编码,数量,位号,备注\nRES-10K,2,R1,示例行，可删除\n';

function downloadTemplate() {
  const blob = new Blob([TEMPLATE_CONTENT], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'bom-import-template.csv';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

export function BomImportModal({
  opened,
  onClose,
  partId,
  onImported
}: Readonly<{
  opened: boolean;
  onClose: () => void;
  partId: number;
  onImported: () => void;
}>) {
  const [file, setFile] = useState<File | null>(null);
  const [updateExisting, setUpdateExisting] = useState<boolean>(true);
  const [uploading, setUploading] = useState<boolean>(false);
  const [result, setResult] = useState<any>(null);

  function reset() {
    setFile(null);
    setResult(null);
    setUploading(false);
  }

  function close() {
    reset();
    onClose();
  }

  function submit() {
    if (!file) return;

    const formData = new FormData();
    formData.append('data_file', file);
    formData.append('update_existing', updateExisting ? 'true' : 'false');

    setUploading(true);
    setResult(null);

    api
      .post(apiUrl(ApiEndpoints.bom_import, partId), formData, {
        timeout: 120 * 1000
      })
      .then((response) => {
        const data = response.data;
        setResult(data);

        notifications.show({
          title: t`BOM Import Complete`,
          message: t`Created: ${data.created}, Updated: ${data.updated}, Errors: ${data.error_count}`,
          color: data.error_count > 0 ? 'orange' : 'green',
          icon: <IconCircleCheck />,
          autoClose: 5000
        });

        onImported();
      })
      .catch((error) => {
        const detail =
          error?.response?.data?.data_file?.[0] ??
          error?.response?.data?.detail ??
          t`Failed to import BOM data`;

        notifications.show({
          title: t`BOM Import Failed`,
          message: String(detail),
          color: 'red',
          icon: <IconExclamationCircle />,
          autoClose: 6000
        });
      })
      .finally(() => {
        setUploading(false);
      });
  }

  return (
    <Modal
      opened={opened}
      onClose={close}
      title={t`Import BOM from File`}
      size='lg'
    >
      <Stack gap='sm'>
        <Text size='sm'>
          {t`Upload a CSV or Excel file to create or update BOM items for this assembly.`}
        </Text>

        <Alert color='blue' variant='light'>
          <Text size='sm'>{t`Supported columns`}</Text>
          <List size='xs' mt={4}>
            <List.Item>
              {t`Component: part IPN or part name (required, e.g. 子件编码 / IPN)`}
            </List.Item>
            <List.Item>{t`Quantity: e.g. 数量 / Quantity`}</List.Item>
            <List.Item>{t`Reference: e.g. 位号 / Reference`}</List.Item>
            <List.Item>{t`Notes: e.g. 备注 / Notes`}</List.Item>
          </List>
          <Anchor size='xs' onClick={downloadTemplate} mt={6}>
            <Group gap={4}>
              <IconDownload size={14} />
              {t`Download CSV template`}
            </Group>
          </Anchor>
        </Alert>

        <FileInput
          label={t`BOM File`}
          description={t`Accepted formats: .csv, .tsv, .xls, .xlsx`}
          placeholder={t`Select a file`}
          value={file}
          onChange={setFile}
          accept='.csv,.tsv,.xls,.xlsx'
          leftSection={<IconFileUpload size={16} />}
          clearable
        />

        <Switch
          label={t`Update existing BOM items`}
          description={t`When disabled, existing items are skipped`}
          checked={updateExisting}
          onChange={(event) => setUpdateExisting(event.currentTarget.checked)}
        />

        {result && (
          <>
            <Divider />
            <Alert
              color={result.error_count > 0 ? 'orange' : 'green'}
              title={t`Import Result`}
            >
              <Text size='sm'>
                {t`Created`}: {result.created} · {t`Updated`}: {result.updated}{' '}
                · {t`Skipped`}: {result.skipped} · {t`Errors`}:{' '}
                {result.error_count}
              </Text>
              {result.error_count > 0 && (
                <List size='xs' mt={6}>
                  {result.errors.slice(0, 10).map((error: any) => (
                    <List.Item key={error.row}>
                      {t`Row`} {error.row}: {error.message}
                    </List.Item>
                  ))}
                </List>
              )}
            </Alert>
          </>
        )}

        <Group justify='flex-end'>
          <Button variant='default' onClick={close}>
            {t`Close`}
          </Button>
          <Button
            leftSection={<IconFileUpload size={16} />}
            onClick={submit}
            loading={uploading}
            disabled={!file}
          >
            {t`Import`}
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
