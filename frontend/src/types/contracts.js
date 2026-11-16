/** @typedef {{id:number,hour:string,pressure:number,flow:number,temperature:number,machines:number,sensor_noise:number,kwh:number,note:string}} Sample */
/** @typedef {{id:number,name:string,features:string[],alphas:number[],state:string,result:object,error:string}} Run */
/** @typedef {{id:number,run_id:number,title:string,finding:string,action:string,status:string}} Review */
/** @typedef {{id:number,name:string,start_hour:string,end_hour:string,price:number}} Tariff */
/** @typedef {{id:number,name:string,run_id:number,start_hour:string,end_hour:string,status:string,settlement_id:number|null,basis_checksum:string}} Pilot */
/** @typedef {{id:number,pilot_id:number,state:'failed'|'settled',total_kwh:number,total_amount:number,basis_checksum:string,gaps:Array<{type:string,hour:string,detail:string}>,created:string,hours?:Array}} Settlement */
