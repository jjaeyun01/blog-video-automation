import React from 'react';
import {Composition, getInputProps} from 'remotion';
import {BlogVideo, BlogVideoManifest} from './components/BlogVideo';

const DEFAULT_DURATION_SECONDS = 55;
const FPS = 30;

export const RemotionRoot: React.FC = () => {
  const props = getInputProps() as Partial<BlogVideoManifest>;
  const durationSeconds =
    props.script?.scenes?.reduce((sum, scene) => sum + scene.duration_sec, 0) ||
    props.script?.target_duration_sec ||
    DEFAULT_DURATION_SECONDS;

  return (
    <Composition
      id="BlogVideo"
      component={BlogVideo}
      durationInFrames={Math.ceil(durationSeconds * FPS)}
      fps={FPS}
      width={1080}
      height={1920}
      defaultProps={props as BlogVideoManifest}
    />
  );
};

export default RemotionRoot;
