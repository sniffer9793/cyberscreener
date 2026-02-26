/**
 * QUAEST.TECH — The World (2D Forum)
 * Pixel-art Roman world where Quaestors walk, talk, and pin Scrolls of Truth.
 * Powered by Phaser 3 embedded in React.
 */

import { useState, useCallback, useRef } from 'react';
import { Card } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { useAuth } from '../auth/AuthContext';
import { PhaserGame } from '../game/PhaserGame';
import { DISTRICTS } from '../game/config';
import styles from './WorldPage.module.css';

export function WorldPage() {
  const { user, profile } = useAuth();
  const gameRef = useRef(null);
  const [currentDistrict, setCurrentDistrict] = useState(null);
  const [dialogLog, setDialogLog] = useState([]);
  const [chatInput, setChatInput] = useState('');

  const onDistrictChange = useCallback((district) => {
    setCurrentDistrict(district);
    if (district) {
      setDialogLog(prev => [
        ...prev.slice(-19),
        { type: 'system', text: `Entered ${district.name}`, time: new Date() },
      ]);
    }
  }, []);

  const onInteract = useCallback((interaction) => {
    setDialogLog(prev => [
      ...prev.slice(-19),
      {
        type: interaction.type,
        name: interaction.name,
        text: interaction.dialog,
        time: new Date(),
      },
    ]);
  }, []);

  const handleChat = (e) => {
    e.preventDefault();
    if (!chatInput.trim()) return;
    setDialogLog(prev => [
      ...prev.slice(-19),
      {
        type: 'player',
        name: profile?.name || user?.email || 'You',
        text: chatInput,
        time: new Date(),
      },
    ]);
    setChatInput('');
  };

  return (
    <div className={styles.layout}>
      {/* Game viewport */}
      <div className={styles.gameContainer}>
        <PhaserGame
          ref={gameRef}
          onDistrictChange={onDistrictChange}
          onInteract={onInteract}
          width={640}
          height={480}
        />

        {/* Controls hint */}
        <div className={styles.controlsBar}>
          <span className={styles.controlKey}>WASD</span> Move
          <span className={styles.controlDivider} />
          <span className={styles.controlKey}>E</span> Interact
          <span className={styles.controlDivider} />
          <span className={styles.controlKey}>Click</span> Walk to
        </div>
      </div>

      {/* Sidebar */}
      <div className={styles.sidebar}>
        {/* District info */}
        <Card style={{ padding: 14 }}>
          <div className={styles.sectionLabel}>Current Location</div>
          {currentDistrict ? (
            <div className={styles.districtInfo}>
              <div className={styles.districtName} style={{ color: currentDistrict.labelColor }}>
                {currentDistrict.name}
              </div>
              <div className={styles.districtDesc}>{currentDistrict.desc}</div>
              {currentDistrict.locked && (
                <Badge color="var(--forge-amber)" variant="soft">
                  Requires {currentDistrict.locked}+ Grade
                </Badge>
              )}
            </div>
          ) : (
            <div className={styles.districtDesc}>Wandering the roads...</div>
          )}
        </Card>

        {/* World map legend */}
        <Card style={{ padding: 14 }}>
          <div className={styles.sectionLabel}>Districts</div>
          <div className={styles.legendList}>
            {DISTRICTS.map(d => (
              <div
                key={d.id}
                className={`${styles.legendItem} ${currentDistrict?.id === d.id ? styles.legendActive : ''}`}
              >
                <span className={styles.legendDot} style={{ background: d.labelColor }} />
                <span className={styles.legendName}>{d.name}</span>
                {d.locked && (
                  <span className={styles.legendLock}>
                    {d.locked}+
                  </span>
                )}
              </div>
            ))}
          </div>
        </Card>

        {/* Chat / Dialog log */}
        <Card style={{ padding: 14, flex: 1, display: 'flex', flexDirection: 'column' }}>
          <div className={styles.sectionLabel}>Scroll Feed</div>
          <div className={styles.chatLog}>
            {dialogLog.length === 0 ? (
              <div className={styles.chatEmpty}>
                Walk up to NPCs and press <strong>E</strong> to interact.
              </div>
            ) : (
              dialogLog.map((msg, i) => (
                <div key={i} className={`${styles.chatMsg} ${styles[`chat_${msg.type}`]}`}>
                  {msg.name && <span className={styles.chatName}>{msg.name}</span>}
                  <span className={styles.chatText}>{msg.text}</span>
                </div>
              ))
            )}
          </div>

          {/* Chat input */}
          <form className={styles.chatForm} onSubmit={handleChat}>
            <input
              className={styles.chatInput}
              type="text"
              placeholder={user ? 'Say something...' : 'Sign in to chat'}
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              disabled={!user}
              onFocus={() => {
                // Prevent game from capturing keystrokes while typing
                const scene = gameRef.current?.getScene('WorldScene');
                if (scene) scene.input.keyboard.enabled = false;
              }}
              onBlur={() => {
                const scene = gameRef.current?.getScene('WorldScene');
                if (scene) scene.input.keyboard.enabled = true;
              }}
            />
            <button className={styles.chatSend} type="submit" disabled={!user || !chatInput.trim()}>
              Send
            </button>
          </form>
        </Card>
      </div>
    </div>
  );
}
