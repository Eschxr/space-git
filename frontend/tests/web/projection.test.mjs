import {test} from 'node:test';
import assert from 'node:assert/strict';
import {validateObjects} from '../../apps/web/app/world/projection-objects.ts';

const object={id:'orb',name:'Blue orb',shape:'sphere',color:'#72d5ef',animation:'float',position:[0,0,0],size:.18};
test('projection plans reject unsafe geometry and preserve valid input without mutation',()=>{
  const state=structuredClone([object]);
  assert.equal(validateObjects(state),state);
  assert.deepEqual(state,[object]);
  assert.deepEqual(validateObjects([]),[]);
  for(const invalid of [null,[object,object],Array.from({length:13},(_,i)=>({...object,id:String(i)})),
    [{...object,position:[NaN,0,0]}],[{...object,position:[0,0,2]}],[{...object,size:Infinity}],
    [{...object,shape:'code'}],[{...object,color:'url(x)'}],[{...object,animation:'script'}]]){
    assert.throws(()=>validateObjects(invalid));
  }
});
