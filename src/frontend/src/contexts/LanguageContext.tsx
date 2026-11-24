import { i18n } from '@lingui/core';
import { I18nProvider } from '@lingui/react';
import { LoadingOverlay, Text } from '@mantine/core';
import { type JSX, useEffect, useRef, useState } from 'react';

import { useStoredTableState } from '@lib/states/StoredTableState';
import { useShallow } from 'zustand/react/shallow';
import { api } from '../App';
import { markLocaleReady } from '../functions/localeReady';
import { useLocalState } from '../states/LocalState';
import { useServerApiState } from '../states/ServerApiState';
import { fetchGlobalStates } from '../states/states';

export const defaultLocale = 'en';

/*
 * Function which returns a record of supported languages.
 * Note that this is not a constant, as it is used in the LanguageSelect component
 */
export const getSupportedLanguages = (): Record<string, string> => {
  return {
    ar: 'العربية',
    bg: 'Български',
    ca: 'Català',
    cs: 'Čeština',
    da: 'Dansk',
    de: 'Deutsch',
    el: 'Ελληνικά',
    en: 'English',
    es: 'Español',
    es_MX: 'Español (México)',
    et: 'Eesti',
    fa: 'فارسی',
    fi: 'Suomi',
    fr: 'Français',
    he: 'עברית',
    hi: 'हिन्दी',
    hu: 'Magyar',
    it: 'Italiano',
    ja: '日本語',
    ko: '한국어',
    lt: 'Lietuvių',
    lv: 'Latviešu',
    nl: 'Nederlands',
    no: 'Norsk',
    pl: 'Polski',
    pt: 'Português',
    pt_BR: 'Português (Brasil)',
    ro: 'Română',
    ru: 'Русский',
    sk: 'Slovenčina',
    sl: 'Slovenščina',
    sr: 'Српски',
    sv: 'Svenska',
    th: 'ไทย',
    tr: 'Türkçe',
    uk: 'Українська',
    vi: 'Tiếng Việt',
    zh_Hans: '中文（简体）',
    zh_Hant: '中文（繁體）'
  };
};

// Normalize a locale identifier (server default locale, stored user preference
// or browser locale) to one of the keys returned by getSupportedLanguages().
// The backend reports Django-style codes such as 'zh-hans', while the compiled
// frontend message catalogs live in directories such as 'zh_Hans'.
export function normalizeLocale(locale: string | null | undefined): string {
  const keys = Object.keys(getSupportedLanguages());

  if (!locale) {
    return defaultLocale;
  }

  const candidate = locale.replaceAll('-', '_');
  const lower = candidate.toLowerCase();

  // Exact match (case-insensitive), e.g. 'zh-hans' -> 'zh_Hans'
  const exact = keys.find((key) => key.toLowerCase() === lower);
  if (exact) {
    return exact;
  }

  // Base language match, e.g. 'zh' -> 'zh_Hans'
  const base = lower.split('_')[0];
  const baseMatch = keys.find(
    (key) => key.toLowerCase().split('_')[0] === base
  );

  return baseMatch ?? defaultLocale;
}

export function LanguageContext({
  children
}: Readonly<{ children: JSX.Element }>) {
  const [language] = useLocalState(useShallow((state) => [state.language]));
  const [server] = useServerApiState(useShallow((state) => [state.server]));

  const [activeLocale, setActiveLocale] = useState<string | null>(null);

  useEffect(() => {
    // Update the locale based on prioritization:
    // 1. Locally selected locale
    // 2. Server default locale
    // 3. English (fallback)

    let locale: string | null = activeLocale;

    if (!!language) {
      locale = language;
    } else if (!!server.default_locale) {
      locale = server.default_locale;
    } else {
      locale = defaultLocale;
    }

    locale = normalizeLocale(locale);

    if (locale != activeLocale) {
      // Activate the catalog first, then commit the locale state. The provider
      // is keyed on the active locale, so the subtree only re-mounts once the
      // new translations are actually loaded (avoids stale English strings).
      activateLocale(locale).then(() => setActiveLocale(locale));
    }
  }, [activeLocale, language, server.default_locale, defaultLocale]);

  const [loadedState, setLoadedState] = useState<
    'loading' | 'loaded' | 'error'
  >('loading');
  const isMounted = useRef(true);

  useEffect(() => {
    isMounted.current = true;

    // Normalize the selected language, falling back to the server default
    const lang: string = normalizeLocale(
      language || server.default_locale || defaultLocale
    );

    activateLocale(lang)
      .then(() => {
        if (isMounted.current) setLoadedState('loaded');

        /*
         * Configure the default Accept-Language header for all requests.
         * - Locally selected locale
         * - Server default locale
         * - en-us (backup)
         */
        const locales: (string | undefined)[] = [];

        if (!!lang && lang != 'pseudo-LOCALE') {
          locales.push(lang);
        }

        if (!!server.default_locale) {
          locales.push(server.default_locale);
        }

        if (locales.indexOf('en-us') < 0) {
          locales.push('en-us');
        }

        // Ensure that the locales are properly formatted
        const new_locales = locales
          .map((locale) => locale?.replaceAll('_', '-').toLowerCase())
          .join(', ');

        if (new_locales == api.defaults.headers.common['Accept-Language']) {
          return;
        }

        // Update default Accept-Language headers
        api.defaults.headers.common['Accept-Language'] = new_locales;

        // Reload server state (and refresh status codes). Forced: the
        // Accept-Language header actually changed (initial set, or a real
        // locale change), so this must not be skipped by the "already
        // fetched" guard even if another caller already fetched once.
        fetchGlobalStates(true);

        // Clear out cached table column names
        useStoredTableState.getState().clearTableColumnNames();
      })
      /* istanbul ignore next */
      .catch((err) => {
        console.error('ERR: Failed loading translations', err);
        if (isMounted.current) setLoadedState('error');
      });

    return () => {
      isMounted.current = false;
    };
  }, [language, server.default_locale]);

  if (loadedState === 'loading') {
    return <LoadingOverlay visible={true} />;
  }

  /* istanbul ignore next */
  if (loadedState === 'error') {
    return (
      <Text>
        An error occurred while loading translations, see browser console for
        details.
      </Text>
    );
  }

  // only render the i18n Provider if the locales are fully activated, otherwise we end
  // up with an error in the browser console.
  // The provider is keyed on the active locale so that all components re-render
  // with the newly loaded catalog (simple `t` calls do not subscribe to changes).
  return (
    <I18nProvider i18n={i18n} key={activeLocale ?? defaultLocale}>
      {children}
    </I18nProvider>
  );
}

// This function is used to determine the locale to activate based on the prioritization rules.
export function getPriorityLocale(): string {
  const serverDefault = useServerApiState.getState().server.default_locale;
  const userDefault = useLocalState.getState().language;

  return normalizeLocale(userDefault || serverDefault || defaultLocale);
}

export async function activateLocale(locale: string | null) {
  // Resolve aliases (e.g. server-side 'zh-hans') to a supported catalog key ('zh_Hans')
  const resolved = normalizeLocale(locale ?? getPriorityLocale());

  try {
    const { messages } = await import(`../locales/${resolved}/messages.ts`);
    i18n.load(resolved, messages);
    i18n.activate(resolved);
    // Keep the document language in sync (accessibility / font selection)
    if (typeof document !== 'undefined') {
      document.documentElement.lang = resolved.replaceAll('_', '-');
    }
    markLocaleReady();
  } catch (err) {
    console.error(`Failed to load locale ${resolved}:`, err);
  }
}
