import streamlit as st
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta

# ==========================================
# 1. LOGIQUE DE CALCUL (MOTEUR IDENTIQUE)
# ==========================================

def _parse_pause(params, start_time_global):
    if not params.get('pause_enabled'):
        return None
    if not params.get('pause_locations'):
        return None
    try:
        pause_start = datetime.strptime(params['pause_time'], "%H:%M")
    except ValueError:
        st.error("Format d'heure invalide pour le temps mort.")
        return None
    pause_duration = timedelta(minutes=params['pause_duration'])
    if pause_duration.total_seconds() <= 0:
        return None
    return {
        'start': pause_start,
        'end': pause_start + pause_duration,
        'duration': pause_duration,
        'locations': params['pause_locations']
    }


def _apply_pause_to_phase(times, pause, phase):
    """Applique la pause à une phase donnée si elle est impactée par le temps mort.
    
    Logique : si l'épreuve chevauche ou commence pendant le temps mort, 
    on la décale pour qu'elle commence APRÈS la fin du temps mort.
    """
    phases = ['dressage', 'cross', 'saut']
    idx = phases.index(phase)
    p_start, p_end = times[phase]
    pause_start = pause['start']
    pause_end = pause['end']
    duration = pause['duration']
    phase_duration = p_end - p_start

    # Si la phase se termine avant ou au début du temps mort → pas d'impact
    if p_end <= pause_start:
        return times
    
    # Si la phase commence pendant ou après le début du temps mort mais avant la fin
    # → la décaler pour commencer après la fin du temps mort
    if p_start >= pause_start and p_start < pause_end:
        new_start = pause_end
        new_end = new_start + phase_duration
        times[phase] = (new_start, new_end)
        # Recalculer les phases suivantes à partir de cette nouvelle fin
        return times
    
    # Si le temps mort tombe PENDANT la phase (la phase a commencé avant le temps mort)
    # → la phase est interrompue et reprend après, donc elle finit plus tard
    if p_start < pause_start < p_end:
        new_end = p_end + duration
        times[phase] = (p_start, new_end)
        return times
    
    # Si la phase commence après la fin du temps mort → pas de décalage direct
    # (le décalage vient des phases précédentes)
    return times


def _apply_pause_to_times(times, pause):
    """Applique le temps mort aux horaires d'un cavalier, seulement si impacté."""
    if not pause:
        return times

    locations = pause['locations']
    pause_start = pause['start']
    pause_end = pause['end']
    
    # Pour chaque lieu impacté, appliquer la pause
    for location in locations:
        if location == 'Dressage':
            times = _apply_pause_to_phase(times, pause, 'dressage')
        elif location == 'Cross':
            times = _apply_pause_to_phase(times, pause, 'cross')
        elif location == 'Saut':
            times = _apply_pause_to_phase(times, pause, 'saut')
        elif location == 'Dressage/Saut (même terrain)':
            times = _apply_pause_to_phase(times, pause, 'dressage')
            times = _apply_pause_to_phase(times, pause, 'saut')
    
    return times


def _build_times(candidat_start, params, pause):
    d_dressage = timedelta(minutes=params['d_dressage'])
    d_cross = timedelta(minutes=params['d_cross'])
    d_saut = timedelta(minutes=params['d_saut'])

    c_dress_start = candidat_start
    c_dress_end = c_dress_start + d_dressage
    c_cross_start = c_dress_end + timedelta(minutes=params['d_pause1'])
    c_cross_end = c_cross_start + d_cross
    c_saut_start = c_cross_end + timedelta(minutes=params['d_pause2'])
    c_saut_end = c_saut_start + d_saut

    times = {
        'dressage': (c_dress_start, c_dress_end),
        'cross': (c_cross_start, c_cross_end),
        'saut': (c_saut_start, c_saut_end)
    }
    return _apply_pause_to_times(times, pause)


def verifier_conflit_individuel(candidat_start, schedule_existant, params, pause=None):
    """Vérifie les conflits selon les paramètres (identique script précédent)"""
    times = _build_times(candidat_start, params, pause)
    c_dress_start, c_dress_end = times['dressage']
    c_cross_start, c_cross_end = times['cross']
    c_saut_start, c_saut_end = times['saut']

    # Vérifier qu'aucune épreuve ne se déroule PENDANT le temps mort (sur les lieux impactés)
    if pause:
        pause_start = pause['start']
        pause_end = pause['end']
        locations = pause['locations']
        
        for loc in locations:
            if loc == 'Dressage' or loc == 'Dressage/Saut (même terrain)':
                # L'épreuve ne peut pas chevaucher le temps mort
                if c_dress_start < pause_end and c_dress_end > pause_start:
                    # Mais c'est OK si elle est complètement avant ou après
                    if not (c_dress_end <= pause_start or c_dress_start >= pause_end):
                        return False
            if loc == 'Cross':
                if c_cross_start < pause_end and c_cross_end > pause_start:
                    if not (c_cross_end <= pause_start or c_cross_start >= pause_end):
                        return False
            if loc == 'Saut' or loc == 'Dressage/Saut (même terrain)':
                if c_saut_start < pause_end and c_saut_end > pause_start:
                    if not (c_saut_end <= pause_start or c_saut_start >= pause_end):
                        return False

    if schedule_existant:
        prev = schedule_existant[-1]
        if c_dress_start < prev['dressage'][1] + timedelta(minutes=params['reset_dressage']): return False
        if c_cross_start < prev['cross'][1] + timedelta(minutes=params['reset_cross']): return False
        if c_saut_start < prev['saut'][1] + timedelta(minutes=params['reset_saut']): return False

    if params['shared_arena']:
        buffer = timedelta(minutes=params['transition_shared'])
        for other in schedule_existant:
            other_saut_start, other_saut_end = other['saut']
            if (c_dress_start < other_saut_end + buffer) and (c_dress_end > other_saut_start - buffer): return False
            other_dress_start, other_dress_end = other['dressage']
            if (c_saut_start < other_dress_end + buffer) and (c_saut_end > other_dress_start - buffer): return False
                
    return True

def calculer_planning(params):
    try:
        start_time_global = datetime.strptime(params['start_time'], "%H:%M")
    except ValueError:
        st.error("Format d'heure invalide.")
        return []

    nb_cavaliers = params['nb_cavaliers']
    schedule = []
    pause = _parse_pause(params, start_time_global)

    if params['mode'] == 'Manuel':
        try:
            raw_intervals = params['manual_list'].replace(' ', '').split(',')
            intervals = [float(x) for x in raw_intervals if x]
        except ValueError:
            st.error("Erreur dans la liste manuelle.")
            return []
        
        if intervals:
            while len(intervals) < nb_cavaliers: intervals.append(intervals[-1])
        else: intervals = [5] * nb_cavaliers
            
        current_start = start_time_global
        for i in range(nb_cavaliers):
            times = _build_times(current_start, params, pause)
            schedule.append({'id': i+1, 'dressage': times['dressage'], 'cross': times['cross'], 'saut': times['saut']})
            if i < len(intervals):
                next_start = current_start + timedelta(minutes=intervals[i])
                # Si le prochain départ tombe pendant le temps mort, le décaler après
                if pause and pause['start'] <= next_start < pause['end']:
                    next_start = pause['end']
                current_start = next_start
        return schedule

    else: # MODE AUTO
        step = timedelta(seconds=30)
        
        progress_bar = st.progress(0)
        
        for i in range(nb_cavaliers):
            start_candidate = schedule[-1]['dressage'][0] + timedelta(minutes=1) if i > 0 else start_time_global
            
            while True:
                if verifier_conflit_individuel(start_candidate, schedule, params, pause): break
                start_candidate += step
                if (start_candidate - start_time_global).total_seconds() > 43200: # 12h max
                    st.error("Impossible de trouver une solution (trop de contraintes).")
                    return []

            times = _build_times(start_candidate, params, pause)
            schedule.append({'id': i+1, 'dressage': times['dressage'], 'cross': times['cross'], 'saut': times['saut']})
            
            progress_bar.progress((i + 1) / nb_cavaliers)
            
        return schedule

# ==========================================
# 2. INTERFACE WEB (STREAMLIT)
# ==========================================

st.set_page_config(page_title="Planning CCE", layout="wide")

st.markdown(
        """
        <style>
            .made-by {
                position: fixed;
                top: 60px;
                right: 20px;
                z-index: 999999;
                background: rgba(255,255,255,0.95);
                padding: 8px 14px;
                border-radius: 8px;
                font-size: 14px;
                box-shadow: 0 2px 12px rgba(0,0,0,0.15);
                border: 1px solid #ddd;
            }
            .made-by a {
                color: #0066cc;
                text-decoration: none;
            }
            .made-by a:hover {
                text-decoration: underline;
            }
            [data-testid="stSidebar"] > div:first-child {
                display: flex;
                flex-direction: column;
                height: 100vh;
            }
            .sidebar-spacer { flex: 1 1 auto; }
        </style>
        <div class="made-by">
            Made by <a href="www.jeremydigard.com" target="_blank">Jérémy Digard</a> for
            <a href="https://www.equissima.ch" target="_blank">Equissima</a>
            2025- 2026
        </div>
        """,
        unsafe_allow_html=True
)

st.title("🏇 Générateur de Planning Concours Complet")
st.markdown("---")

# --- BARRE LATERALE (PARAMETRES) ---
with st.sidebar:
    st.header("1. Configuration")
    start_time = st.text_input("Heure de début", "12:15")
    nb_cavaliers = st.number_input("Nombre de cavaliers", min_value=1, value=10)
    
    st.subheader("Durées (minutes)")
    d_dressage = st.number_input("Dressage", value=4.0)
    d_pause1 = st.number_input("Pause 1 (vers Cross)", value=15.0)
    d_cross = st.number_input("Cross", value=4.0)
    d_pause2 = st.number_input("Pause 2 (vers Saut)", value=7.0)
    d_saut = st.number_input("Saut", value=2.0)
    
    st.markdown("---")
    st.header("2. Mode de Calcul")
    mode = st.radio("Méthode :", ["Manuel", "Optimisation Auto"], index=1)

    manual_list = ""
    reset_dressage, reset_cross, reset_saut = 0.0, 0.0, 0.0
    shared_arena, transition_shared = True, 0.0

    if mode == "Manuel":
        manual_list = st.text_input("Liste des écarts (ex: 6, 7, 4)", "6, 7, 4")
    else:
        st.info("Temps de remise en état (Reset) entre 2 cavaliers :")
        col1, col2, col3 = st.columns(3)
        with col1: reset_dressage = st.number_input("Reset Dress.", value=1.0)
        with col2: reset_cross = st.number_input("Reset Cross", value=2.0)
        with col3: reset_saut = st.number_input("Reset Saut", value=1.5)
        
        shared_arena = st.checkbox("Même terrain (Dressage / Saut)", value=True)
        if shared_arena:
            transition_shared = st.number_input("Temps transition D/S", value=5.0)

    st.markdown("---")
    st.header("3. Temps morts (accident/maintenance)")
    pause_enabled = st.checkbox("Activer un temps mort")
    pause_time = ""
    pause_duration = 0.0
    pause_locations = []
    if pause_enabled:
        pause_time = st.text_input("Horaire du temps mort", "14:30")
        pause_duration = st.number_input("Durée (minutes)", min_value=0.0, value=10.0)
        st.write("Lieu(x) du temps mort :")
        if shared_arena:
            if st.checkbox("Dressage/Saut (même terrain)", key="pause_dress_saut"):
                pause_locations.append("Dressage/Saut (même terrain)")
            if st.checkbox("Cross", key="pause_cross"):
                pause_locations.append("Cross")
        else:
            if st.checkbox("Dressage", key="pause_dressage"):
                pause_locations.append("Dressage")
            if st.checkbox("Cross", key="pause_cross"):
                pause_locations.append("Cross")
            if st.checkbox("Saut", key="pause_saut"):
                pause_locations.append("Saut")

    st.markdown('<div class="sidebar-spacer"></div>', unsafe_allow_html=True)

    generate_btn = st.button("Générer le Planning", type="primary", use_container_width=True)

# --- CORPS PRINCIPAL ---

if generate_btn:
    params = {
        'start_time': start_time, 'nb_cavaliers': int(nb_cavaliers),
        'd_dressage': d_dressage, 'd_pause1': d_pause1,
        'd_cross': d_cross, 'd_pause2': d_pause2, 'd_saut': d_saut,
        'mode': mode, 'manual_list': manual_list,
        'reset_dressage': reset_dressage, 'reset_cross': reset_cross, 'reset_saut': reset_saut,
        'shared_arena': shared_arena, 'transition_shared': transition_shared,
        'pause_enabled': pause_enabled, 'pause_time': pause_time,
        'pause_duration': pause_duration, 'pause_locations': pause_locations
    }

    schedule = calculer_planning(params)

    if schedule:
        # Affichage du graphe
        fig, ax = plt.subplots(figsize=(12, nb_cavaliers * 0.5 + 2)) # Hauteur dynamique
        colors = {'dressage': '#4472C4', 'cross': '#548235', 'saut': '#C00000'}
        bar_height = 0.5
        
        for cav in schedule:
            y = cav['id']
            # Dressage
            start, end = mdates.date2num(cav['dressage'][0]), mdates.date2num(cav['dressage'][1])
            ax.barh(y, end - start, left=start, height=bar_height, color=colors['dressage'], edgecolor='white')
            ax.text(start, y - 0.35, cav['dressage'][0].strftime("%H:%M"), fontsize=8, ha='center', fontweight='bold')
            # Cross
            start, end = mdates.date2num(cav['cross'][0]), mdates.date2num(cav['cross'][1])
            ax.barh(y, end - start, left=start, height=bar_height, color=colors['cross'], edgecolor='white')
            ax.text(start, y - 0.35, cav['cross'][0].strftime("%H:%M"), fontsize=8, ha='center', fontweight='bold')
            # Saut
            start, end = mdates.date2num(cav['saut'][0]), mdates.date2num(cav['saut'][1])
            ax.barh(y, end - start, left=start, height=bar_height, color=colors['saut'], edgecolor='white')
            ax.text(start, y - 0.35, cav['saut'][0].strftime("%H:%M"), fontsize=8, ha='center', fontweight='bold')

        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        ax.xaxis.set_major_locator(mdates.MinuteLocator(interval=15))
        ax.set_yticks([c['id'] for c in schedule])
        ax.set_yticklabels([f"Cavalier {c['id']}" for c in schedule], fontweight='bold')
        ax.invert_yaxis()
        ax.grid(True, axis='x', linestyle='--', alpha=0.5)
        
        # Légende manuelle pour Matplotlib dans Streamlit
        legend_elements = [
            plt.Rectangle((0,0),1,1, color=colors['dressage'], label='Dressage'),
            plt.Rectangle((0,0),1,1, color=colors['cross'], label='Cross'),
            plt.Rectangle((0,0),1,1, color=colors['saut'], label='Saut (CSO)')
        ]
        ax.legend(handles=legend_elements, loc='upper center', bbox_to_anchor=(0.5, -0.05), ncol=3)
        
        st.pyplot(fig)
        st.success(f"Planning généré pour {nb_cavaliers} cavaliers !")
