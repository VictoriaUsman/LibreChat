import React from 'react';
import { RecoilRoot, useRecoilValue } from 'recoil';
import { renderHook, waitFor } from '@testing-library/react';

import store from '../settings';

const Wrapper = ({ children }: { children: React.ReactNode }) => (
  <RecoilRoot>{children}</RecoilRoot>
);

describe('engineTTS', () => {
  afterEach(() => {
    localStorage.clear();
  });

  it('defaults to external so read-aloud uses the configured TTS provider, not the browser voice', async () => {
    const { result } = renderHook(() => useRecoilValue(store.engineTTS), { wrapper: Wrapper });

    await waitFor(() => expect(result.current).toBe('external'));
  });

  it('yields to a value the user previously chose in Settings', async () => {
    localStorage.setItem('engineTTS', JSON.stringify('browser'));

    const { result } = renderHook(() => useRecoilValue(store.engineTTS), { wrapper: Wrapper });

    await waitFor(() => expect(result.current).toBe('browser'));
  });

  it('is not persisted until the user changes it, so the default reaches every untouched profile', async () => {
    const { result } = renderHook(() => useRecoilValue(store.engineTTS), { wrapper: Wrapper });

    await waitFor(() => expect(result.current).toBe('external'));
    expect(localStorage.getItem('engineTTS')).toBeNull();
  });
});
