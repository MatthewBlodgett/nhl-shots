/* Pure freshness calculations shared by the static dashboard and browser tests. */
(function(root){
  const validTime=value=>{if(typeof value!=='string'||!/(Z|[+-]\d{2}:\d{2})$/.test(value))return NaN;return Date.parse(value)};
  function ageQuotes(result,now){
    for(const q of result.observations||[]){
      const updated=validTime(q.book_updated_at),start=validTime(q.game_start);
      const age=(now-updated)/1000;
      q.age_seconds_now=Number.isFinite(age)?age:null;
      q.expired_now=!Number.isFinite(age)||age>600||age< -60||!Number.isFinite(start)||start<=now;
    }
    result.as_of=new Date(now).toISOString();return result;
  }
  function ageSummary(input,now=Date.now()){
    if(input?.schema_version!==1||!input.status||!Array.isArray(input.candidates?.observations)||!input.performance?.versions||!input.players||!input.research)throw Error('Unsupported archive summary');
    const data=JSON.parse(JSON.stringify(input));const recorded=validTime(data.status.last_run?.recorded_at);
    const age=(now-recorded)/1000;
    data.status.last_attempt_age_seconds=Number.isFinite(age)?age:null;
    data.status.stale=!Number.isFinite(age)||age>7200||age< -60;
    data.status.as_of=new Date(now).toISOString();ageQuotes(data.candidates,now);
    for(const value of Object.values(data.players))ageQuotes(value,now);
    return data;
  }
  const api={ageQuotes,ageSummary};root.NHLReview=api;
  if(typeof module!=='undefined')module.exports=api;
})(typeof window!=='undefined'?window:globalThis);
