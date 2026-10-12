import fs from 'fs';
import { computeContractHash } from './contract';
it('hash', () => {
  const t = fs.readFileSync(__dirname + '/__fixtures__/cxone-contract.json', 'utf8');
  expect(computeContractHash(t)).toBe('b641cd4adaee6c9bb98b4db229c2cc182ff143c184b6c9faa6170db3abdb48e8');
});
