import React from 'react';
import {
  AbsoluteFill,
  Audio,
  Sequence,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';

type Scene = {
  index: number;
  duration_sec: number;
  narration: string;
  subtitle: string;
  visual_prompt: string;
  visual_type: string;
};

export type BlogVideoManifest = {
  article: {
    title: string;
    thumbnail_url?: string | null;
  };
  script: {
    title: string;
    hook: string;
    outro: string;
    disclaimer: string;
    target_duration_sec: number;
    scenes: Scene[];
  };
  audio_static_path?: string | null;
};

const COLORS = {
  ink: '#17202A',
  muted: '#506170',
  teal: '#0B8F8A',
  mint: '#D9F4EF',
  yellow: '#F7C948',
  white: '#FFFFFF',
  line: '#D7E6E1',
};

export const BlogVideo: React.FC<BlogVideoManifest> = ({
  article,
  script,
  audio_static_path,
}) => {
  const scenes = script.scenes ?? [];
  const {fps} = useVideoConfig();
  let startFrame = 0;

  return (
    <AbsoluteFill style={styles.page}>
      {audio_static_path ? <Audio src={staticFile(audio_static_path)} /> : null}
      <Header title="FeverCoach" />
      {scenes.map((scene) => {
        const duration = Math.max(1, Math.round(scene.duration_sec * fps));
        const sequence = (
          <Sequence
            key={scene.index}
            from={startFrame}
            durationInFrames={duration}
          >
            <SceneCard scene={scene} articleTitle={article.title} />
          </Sequence>
        );
        startFrame += duration;
        return sequence;
      })}
      <Footer disclaimer={script.disclaimer} />
    </AbsoluteFill>
  );
};

const Header: React.FC<{title: string}> = ({title}) => (
  <div style={styles.header}>
    <div style={styles.logoMark}>F</div>
    <div style={styles.logoText}>{title}</div>
  </div>
);

const Footer: React.FC<{disclaimer: string}> = ({disclaimer}) => (
  <div style={styles.footer}>{disclaimer}</div>
);

const SceneCard: React.FC<{scene: Scene; articleTitle: string}> = ({
  scene,
  articleTitle,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const enter = spring({frame, fps, config: {damping: 18, stiffness: 130}});
  const opacity = interpolate(frame, [0, 10], [0, 1], {
    extrapolateRight: 'clamp',
  });

  return (
    <AbsoluteFill style={styles.sceneWrap}>
      <div
        style={{
          ...styles.scene,
          opacity,
          transform: `translateY(${interpolate(enter, [0, 1], [36, 0])}px)`,
        }}
      >
        <div style={styles.kicker}>부모 건강 정보</div>
        <h1 style={styles.title}>{articleTitle.replace(/^Q:\s*/, '')}</h1>
        <div style={styles.divider} />
        <p style={styles.subtitle}>{scene.subtitle}</p>
        <p style={styles.narration}>{scene.narration}</p>
      </div>
      <div style={styles.sceneNumber}>{String(scene.index).padStart(2, '0')}</div>
    </AbsoluteFill>
  );
};

const styles: Record<string, React.CSSProperties> = {
  page: {
    background: COLORS.white,
    color: COLORS.ink,
    fontFamily:
      'Pretendard, Apple SD Gothic Neo, Noto Sans KR, Arial, sans-serif',
  },
  header: {
    position: 'absolute',
    top: 54,
    left: 64,
    right: 64,
    display: 'flex',
    alignItems: 'center',
    gap: 18,
    zIndex: 10,
  },
  logoMark: {
    width: 54,
    height: 54,
    borderRadius: 14,
    background: COLORS.teal,
    color: COLORS.white,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: 31,
    fontWeight: 800,
  },
  logoText: {
    fontSize: 34,
    fontWeight: 800,
    color: COLORS.teal,
  },
  sceneWrap: {
    justifyContent: 'center',
    padding: '168px 70px 180px',
  },
  scene: {
    border: `3px solid ${COLORS.line}`,
    borderRadius: 32,
    padding: '64px 58px',
    background: `linear-gradient(180deg, ${COLORS.white} 0%, ${COLORS.mint} 100%)`,
    boxShadow: '0 26px 80px rgba(11, 143, 138, 0.13)',
  },
  kicker: {
    display: 'inline-flex',
    alignItems: 'center',
    padding: '12px 18px',
    borderRadius: 999,
    background: COLORS.yellow,
    fontSize: 28,
    fontWeight: 800,
    color: COLORS.ink,
    marginBottom: 34,
  },
  title: {
    fontSize: 58,
    lineHeight: 1.18,
    margin: 0,
    letterSpacing: 0,
  },
  divider: {
    width: 96,
    height: 8,
    borderRadius: 99,
    background: COLORS.teal,
    margin: '42px 0',
  },
  subtitle: {
    fontSize: 48,
    lineHeight: 1.32,
    fontWeight: 800,
    color: COLORS.teal,
    margin: '0 0 32px',
  },
  narration: {
    fontSize: 34,
    lineHeight: 1.55,
    color: COLORS.muted,
    margin: 0,
  },
  sceneNumber: {
    position: 'absolute',
    right: 72,
    bottom: 156,
    fontSize: 42,
    fontWeight: 900,
    color: COLORS.line,
  },
  footer: {
    position: 'absolute',
    left: 64,
    right: 64,
    bottom: 54,
    borderTop: `2px solid ${COLORS.line}`,
    paddingTop: 22,
    fontSize: 24,
    lineHeight: 1.35,
    color: COLORS.muted,
  },
};
