import { expect, test } from 'vitest';
import { parseParameterJson } from './parameterJson';
test('duplicate and escaped-equivalent keys reject, nested distinct values preserve false and zero', () => {
  for (const text of ['{"seed":1,"seed":2}', '{"custom_params":{"x":0,"x":false}}', '{"seed":0,"\\u0073eed":1}', '[]', 'null']) expect(() => parseParameterJson(text)).toThrow();
  expect(parseParameterJson('{"stop":["a,b", "x"], "custom_params":{"x":false,"y":{"x":0}}}')).toEqual({ stop: ['a,b', 'x'], custom_params: { x: false, y: { x: 0 } } });
});
