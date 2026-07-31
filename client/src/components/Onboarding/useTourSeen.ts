import { LocalStorageKeys } from 'librechat-data-provider';
import useLocalStorage from '~/hooks/useLocalStorage';

export default function useTourSeen(): [boolean, (seen: boolean) => void] {
  return useLocalStorage<boolean>(LocalStorageKeys.GUIDED_TOUR_SEEN, false);
}
