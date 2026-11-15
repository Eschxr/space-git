export type Representation='original'|'cleaned'|'mesh';
export type SurfaceSettings={
  outliers:boolean;outlier_strength:number;voxel:number;depth:number;density_percent:number;
  support:number;smoothing:number;smoothing_intensity:number;
};
export type SurfaceAction='analyse'|'reconstruct'|'smooth';
export type SurfaceReport={
  input:{points:number;color:boolean;spacing:number;dimensions:number[];isolated:number;units:string};
  cleaned_points?:number;recommended_depth:number;seconds?:number;warnings:string[];
  mesh?:{vertices:number;triangles:number;components:number;supported_fraction:number};
};
export type SurfaceJob={
  id:string;source:string;model:boolean;action:SurfaceAction;
  status:'queued'|'running'|'complete'|'failed'|'cancelled';slots:number[];
  completed:number;stage:string;slot?:number;error?:string;applied?:boolean;reports?:Record<string,SurfaceReport>;
};
export type ViewStyle={pointSize:number;pointOpacity:number;meshOpacity:number;colour:number;lighting:number;background:string};
export const originalView:ViewStyle={pointSize:1,pointOpacity:1,meshOpacity:1,colour:1,lighting:1,background:'#111111'};
