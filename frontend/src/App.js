import React, { useState, useRef, useEffect } from 'react';
import './App.css';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

function App() {
  // States
  const [currentView, setCurrentView] = useState('home');
  const [cameraActive, setCameraActive] = useState(false);
  const [capturedImage, setCapturedImage] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [foodAnalysis, setFoodAnalysis] = useState(null);
  const [foodLogs, setFoodLogs] = useState([]);
  const [dailyTotals, setDailyTotals] = useState({ calories: 0, protein: 0, carbs: 0, fat: 0 });
  const [weightGrams, setWeightGrams] = useState(100);
  const [userProfile, setUserProfile] = useState({
    age: 25,
    height: 170,
    weight: 70,
    gender: 'male',
    activity_level: 'moderately_active'
  });
  const [calorieGoal, setCalorieGoal] = useState(2000);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [authToken, setAuthToken] = useState(null);
  const [userStats, setUserStats] = useState({ streak_count: 0, total_foods_logged: 0, badges: [] });
  const [bluetoothSupported, setBluetoothSupported] = useState(false);
  const [bluetoothConnected, setBluetoothConnected] = useState(false);
  const [bluetoothDevice, setBluetoothDevice] = useState(null);
  const [currentScaleWeight, setCurrentScaleWeight] = useState(null);
  const [bluetoothCharacteristic, setBluetoothCharacteristic] = useState(null);
  const [loginForm, setLoginForm] = useState({ email: '', password: '' });
  const [registerForm, setRegisterForm] = useState({
    email: '', password: '', name: '', age: 25, height: 170, weight: 70, 
    gender: 'male', activity_level: 'moderately_active', goal_weight: null
  });
  const [showNewBadges, setShowNewBadges] = useState([]);

  // Refs
  const videoRef = useRef(null);
  const canvasRef = useRef(null);

  // Load data and check authentication on mount
  useEffect(() => {
    const token = localStorage.getItem('authToken');
    if (token) {
      setAuthToken(token);
      setIsAuthenticated(true);
      loadFoodLogs();
      loadUserStats();
    }
    
    // Check Bluetooth support
    if (navigator.bluetooth) {
      setBluetoothSupported(true);
    }
  }, []);

  // Calculate calorie goal when profile changes
  useEffect(() => {
    if (isAuthenticated) {
      calculateCalorieGoal();
    }
  }, [userProfile, isAuthenticated]);

  // Authentication Functions
  const handleLogin = async (e) => {
    e.preventDefault();
    try {
      const response = await fetch(`${BACKEND_URL}/api/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(loginForm)
      });

      if (!response.ok) {
        throw new Error('Login failed');
      }

      const data = await response.json();
      const token = data.access_token;
      
      localStorage.setItem('authToken', token);
      setAuthToken(token);
      setIsAuthenticated(true);
      setCurrentView('home');
      
      loadFoodLogs();
      loadUserStats();
    } catch (error) {
      alert('Login failed: ' + error.message);
    }
  };

  const handleRegister = async (e) => {
    e.preventDefault();
    try {
      const response = await fetch(`${BACKEND_URL}/api/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(registerForm)
      });

      if (!response.ok) {
        throw new Error('Registration failed');
      }

      const data = await response.json();
      const token = data.access_token;
      
      localStorage.setItem('authToken', token);
      setAuthToken(token);
      setIsAuthenticated(true);
      setCurrentView('home');
      
      loadFoodLogs();
      loadUserStats();
    } catch (error) {
      alert('Registration failed: ' + error.message);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('authToken');
    setAuthToken(null);
    setIsAuthenticated(false);
    setCurrentView('login');
    
    // Disconnect Bluetooth if connected
    if (bluetoothConnected && bluetoothDevice) {
      bluetoothDevice.gatt.disconnect();
      setBluetoothConnected(false);
      setBluetoothDevice(null);
    }
  };

  // Bluetooth Functions
  const connectBluetoothScale = async () => {
    if (!bluetoothSupported) {
      alert('Bluetooth is not supported in this browser');
      return;
    }

    try {
      // Request device with Weight Scale Service
      const device = await navigator.bluetooth.requestDevice({
        filters: [
          { services: [0x181D] } // Weight Scale Service
        ]
      });

      const server = await device.gatt.connect();
      setBluetoothDevice(device);
      setBluetoothConnected(true);

      // Listen for disconnection
      device.addEventListener('gattserverdisconnected', () => {
        setBluetoothConnected(false);
        setBluetoothDevice(null);
      });

      // Get Weight Scale service
      const service = await server.getPrimaryService(0x181D);
      const characteristic = await service.getCharacteristic(0x2A9D); // Weight Measurement

      // Start notifications
      await characteristic.startNotifications();
      characteristic.addEventListener('characteristicvaluechanged', handleWeightMeasurement);
      
      alert('Bluetooth scale connected successfully!');
    } catch (error) {
      console.error('Bluetooth connection failed:', error);
      alert('Failed to connect to Bluetooth scale: ' + error.message);
    }
  };

  const handleWeightMeasurement = async (event) => {
    const value = event.target.value;
    
    // Parse weight measurement (simplified implementation)
    const flags = value.getUint8(0);
    const weightRaw = value.getUint16(1, true); // little-endian
    
    // Calculate weight based on flags
    const imperialUnits = Boolean(flags & 0x01);
    let weight;
    
    if (imperialUnits) {
      weight = weightRaw * 0.01; // 0.01 lb resolution
    } else {
      weight = weightRaw * 0.005; // 0.005 kg resolution
    }
    
    // Convert to grams
    const weightInGrams = imperialUnits ? weight * 453.592 : weight * 1000;
    
    // Send to backend
    try {
      await fetch(`${BACKEND_URL}/api/bluetooth-weight`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${authToken}`
        },
        body: JSON.stringify({
          weight_grams: Math.round(weightInGrams),
          user_id: 'default_user' // Replace with actual user ID
        })
      });
      
      // Update weight input for food analysis
      setWeightGrams(Math.round(weightInGrams));
      alert(`Weight updated: ${weight.toFixed(1)} ${imperialUnits ? 'lb' : 'kg'}`);
    } catch (error) {
      console.error('Failed to record weight:', error);
    }
  };

  // Camera Functions
  const startCamera = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ 
        video: { 
          facingMode: 'environment',
          width: { ideal: 1920 },
          height: { ideal: 1080 }
        } 
      });
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        setCameraActive(true);
      }
    } catch (error) {
      console.error('Error accessing camera:', error);
      alert('Could not access camera. Please ensure camera permissions are granted.');
    }
  };

  const stopCamera = () => {
    if (videoRef.current && videoRef.current.srcObject) {
      const stream = videoRef.current.srcObject;
      const tracks = stream.getTracks();
      tracks.forEach(track => track.stop());
      videoRef.current.srcObject = null;
    }
    setCameraActive(false);
  };

  const capturePhoto = () => {
    if (videoRef.current && canvasRef.current) {
      const video = videoRef.current;
      const canvas = canvasRef.current;
      const context = canvas.getContext('2d');

      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;

      context.drawImage(video, 0, 0, canvas.width, canvas.height);
      
      const imageDataUrl = canvas.toDataURL('image/jpeg', 0.8);
      setCapturedImage(imageDataUrl);
      stopCamera();
      setCurrentView('analysis');
    }
  };

  // Food Analysis Functions
  const analyzeFood = async () => {
    if (!capturedImage) return;

    setAnalyzing(true);
    try {
      const response = await fetch(`${BACKEND_URL}/api/analyze-food`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          image_base64: capturedImage,
          weight_grams: weightGrams
        })
      });

      if (!response.ok) {
        throw new Error('Analysis failed');
      }

      const result = await response.json();
      setFoodAnalysis(result);
    } catch (error) {
      console.error('Analysis error:', error);
      alert('Failed to analyze food. Please try again.');
    } finally {
      setAnalyzing(false);
    }
  };

  const logFood = async () => {
    if (!foodAnalysis || !capturedImage) return;

    try {
      const formData = new FormData();
      formData.append('food_name', foodAnalysis.food_name);
      formData.append('total_calories', foodAnalysis.total_calories);
      formData.append('protein', foodAnalysis.protein);
      formData.append('carbs', foodAnalysis.carbs);
      formData.append('fat', foodAnalysis.fat);
      formData.append('weight_grams', weightGrams);
      formData.append('image_base64', capturedImage);
      formData.append('user_id', 'default_user');

      const response = await fetch(`${BACKEND_URL}/api/log-food`, {
        method: 'POST',
        body: formData
      });

      if (!response.ok) {
        throw new Error('Failed to log food');
      }

      const result = await response.json();
      
      // Check for new badges
      if (result.new_badges && result.new_badges.length > 0) {
        setShowNewBadges(result.new_badges);
        setTimeout(() => setShowNewBadges([]), 3000);
      }

      alert('Food logged successfully!');
      loadFoodLogs();
      loadUserStats();
      setCurrentView('logs');
      setCapturedImage(null);
      setFoodAnalysis(null);
    } catch (error) {
      console.error('Logging error:', error);
      alert('Failed to log food. Please try again.');
    }
  };

  const loadFoodLogs = async () => {
    try {
      console.log('Loading food logs from:', `${BACKEND_URL}/api/food-logs/default_user`);
      const today = new Date().toISOString().split('T')[0];
      const response = await fetch(`${BACKEND_URL}/api/food-logs/default_user?date_filter=${today}`);
      
      console.log('Response status:', response.status);
      if (!response.ok) {
        throw new Error('Failed to load logs');
      }

      const data = await response.json();
      console.log('Loaded logs data:', data);
      setFoodLogs(data.logs);
      setDailyTotals(data.daily_totals);
    } catch (error) {
      console.error('Load logs error:', error);
    }
  };

  const loadUserStats = async () => {
    try {
      const response = await fetch(`${BACKEND_URL}/api/user-stats/default_user`);
      
      if (!response.ok) {
        throw new Error('Failed to load user stats');
      }

      const data = await response.json();
      setUserStats(data);
    } catch (error) {
      console.error('Load user stats error:', error);
    }
  };

  const deleteLog = async (logId) => {
    try {
      const response = await fetch(`${BACKEND_URL}/api/food-logs/${logId}`, {
        method: 'DELETE'
      });

      if (!response.ok) {
        throw new Error('Failed to delete log');
      }

      loadFoodLogs();
      loadUserStats();
    } catch (error) {
      console.error('Delete error:', error);
      alert('Failed to delete food log.');
    }
  };

  const calculateCalorieGoal = async () => {
    try {
      console.log('Calculating calorie goal with profile:', userProfile);
      console.log('Backend URL:', BACKEND_URL);
      
      const response = await fetch(`${BACKEND_URL}/api/calculate-calorie-goal`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(userProfile)
      });

      console.log('Calorie goal response status:', response.status);
      if (!response.ok) {
        throw new Error('Failed to calculate calorie goal');
      }

      const result = await response.json();
      console.log('Calorie goal result:', result);
      setCalorieGoal(result.daily_calorie_goal);
    } catch (error) {
      console.error('Calorie goal calculation error:', error);
    }
  };

  // Render Functions
  const renderLogin = () => (
    <div className="auth-view">
      <div className="auth-container">
        <h1>Login</h1>
        <form onSubmit={handleLogin}>
          <input
            type="email"
            placeholder="Email"
            value={loginForm.email}
            onChange={(e) => setLoginForm({...loginForm, email: e.target.value})}
            required
          />
          <input
            type="password"
            placeholder="Password"
            value={loginForm.password}
            onChange={(e) => setLoginForm({...loginForm, password: e.target.value})}
            required
          />
          <button type="submit" className="btn-primary">Login</button>
        </form>
        <p>
          Don't have an account? 
          <button 
            className="btn-link" 
            onClick={() => setCurrentView('register')}
          >
            Register here
          </button>
        </p>
      </div>
    </div>
  );

  const renderRegister = () => (
    <div className="auth-view">
      <div className="auth-container">
        <h1>Register</h1>
        <form onSubmit={handleRegister}>
          <input
            type="text"
            placeholder="Full Name"
            value={registerForm.name}
            onChange={(e) => setRegisterForm({...registerForm, name: e.target.value})}
            required
          />
          <input
            type="email"
            placeholder="Email"
            value={registerForm.email}
            onChange={(e) => setRegisterForm({...registerForm, email: e.target.value})}
            required
          />
          <input
            type="password"
            placeholder="Password"
            value={registerForm.password}
            onChange={(e) => setRegisterForm({...registerForm, password: e.target.value})}
            required
          />
          <div className="form-row">
            <input
              type="number"
              placeholder="Age"
              value={registerForm.age}
              onChange={(e) => setRegisterForm({...registerForm, age: parseInt(e.target.value)})}
              required
            />
            <select
              value={registerForm.gender}
              onChange={(e) => setRegisterForm({...registerForm, gender: e.target.value})}
            >
              <option value="male">Male</option>
              <option value="female">Female</option>
            </select>
          </div>
          <div className="form-row">
            <input
              type="number"
              placeholder="Height (cm)"
              value={registerForm.height}
              onChange={(e) => setRegisterForm({...registerForm, height: parseFloat(e.target.value)})}
              required
            />
            <input
              type="number"
              placeholder="Weight (kg)"
              value={registerForm.weight}
              onChange={(e) => setRegisterForm({...registerForm, weight: parseFloat(e.target.value)})}
              required
            />
          </div>
          <select
            value={registerForm.activity_level}
            onChange={(e) => setRegisterForm({...registerForm, activity_level: e.target.value})}
          >
            <option value="sedentary">Sedentary</option>
            <option value="lightly_active">Lightly Active</option>
            <option value="moderately_active">Moderately Active</option>
            <option value="very_active">Very Active</option>
            <option value="extra_active">Extra Active</option>
          </select>
          <input
            type="number"
            placeholder="Goal Weight (kg) - Optional"
            value={registerForm.goal_weight || ''}
            onChange={(e) => setRegisterForm({...registerForm, goal_weight: e.target.value ? parseFloat(e.target.value) : null})}
          />
          <button type="submit" className="btn-primary">Register</button>
        </form>
        <p>
          Already have an account? 
          <button 
            className="btn-link" 
            onClick={() => setCurrentView('login')}
          >
            Login here
          </button>
        </p>
      </div>
    </div>
  );

  const renderHome = () => (
    <div className="home-view">
      <div className="hero-section">
        <div className="header-bar">
          <h1 className="hero-title">Food Calorie Tracker</h1>
          <div className="header-actions">
            {bluetoothSupported && (
              <button 
                className={`btn-bluetooth ${bluetoothConnected ? 'connected' : ''}`}
                onClick={connectBluetoothScale}
                disabled={bluetoothConnected}
              >
                {bluetoothConnected ? '📡 Scale Connected' : '⚖️ Connect Scale'}
              </button>
            )}
            <button className="btn-secondary" onClick={() => setCurrentView('stats')}>
              📊 Stats
            </button>
            <button className="btn-secondary" onClick={handleLogout}>
              🚪 Logout
            </button>
          </div>
        </div>
        
        <p className="hero-subtitle">
          Snap a photo of your food and instantly get detailed nutritional information
        </p>
        
        {/* New Badge Notifications */}
        {showNewBadges.length > 0 && (
          <div className="badge-notification">
            <h3>🎉 New Badge{showNewBadges.length > 1 ? 's' : ''} Earned!</h3>
            {showNewBadges.map((badge, index) => (
              <div key={index} className="badge-item">
                🏆 {badge.replace('_', ' ').toUpperCase()}
              </div>
            ))}
          </div>
        )}
        
        <div className="daily-summary">
          <h3>Today's Progress</h3>
          <div className="progress-card">
            <div className="calorie-circle">
              <div className="calorie-number">{Math.round(dailyTotals.calories)}</div>
              <div className="calorie-goal">/ {calorieGoal} cal</div>
            </div>
            <div className="macro-breakdown">
              <div className="macro-item">
                <span className="macro-label">Protein</span>
                <span className="macro-value">{dailyTotals.protein}g</span>
              </div>
              <div className="macro-item">
                <span className="macro-label">Carbs</span>
                <span className="macro-value">{dailyTotals.carbs}g</span>
              </div>
              <div className="macro-item">
                <span className="macro-label">Fat</span>
                <span className="macro-value">{dailyTotals.fat}g</span>
              </div>
            </div>
          </div>
          
          {/* Streak Display */}
          <div className="streak-display">
            <div className="streak-item">
              <span className="streak-icon">🔥</span>
              <span className="streak-text">{userStats.streak_count} Day Streak</span>
            </div>
            <div className="streak-item">
              <span className="streak-icon">📝</span>
              <span className="streak-text">{userStats.total_foods_logged} Foods Logged</span>
            </div>
          </div>
        </div>

        <div className="action-buttons">
          <button 
            className="btn-primary"
            onClick={() => setCurrentView('camera')}
          >
            📱 Take Food Photo
          </button>
          <button 
            className="btn-secondary"
            onClick={() => setCurrentView('logs')}
          >
            📊 View Logs
          </button>
        </div>
      </div>
    </div>
  );

  const renderStats = () => (
    <div className="stats-view">
      <div className="stats-header">
        <button 
          className="btn-back"
          onClick={() => setCurrentView('home')}
        >
          ← Back
        </button>
        <h2>Your Stats & Achievements</h2>
      </div>
      
      <div className="stats-container">
        <div className="stats-card">
          <h3>🔥 Current Streak</h3>
          <div className="stat-number">{userStats.streak_count} days</div>
        </div>
        
        <div className="stats-card">
          <h3>📝 Foods Logged</h3>
          <div className="stat-number">{userStats.total_foods_logged}</div>
        </div>
        
        <div className="badges-section">
          <h3>🏆 Badges Earned</h3>
          <div className="badges-grid">
            {userStats.badges && userStats.badges.length > 0 ? 
              userStats.badges.map((badge, index) => (
                <div key={index} className="badge-card">
                  <div className="badge-icon">🏆</div>
                  <div className="badge-name">{badge.name}</div>
                  <div className="badge-description">{badge.description}</div>
                </div>
              )) :
              <p className="no-badges">No badges earned yet. Keep logging to earn your first badge!</p>
            }
          </div>
        </div>
      </div>
    </div>
  );

  const renderCamera = () => (
    <div className="camera-view">
      <div className="camera-header">
        <button 
          className="btn-back"
          onClick={() => {
            stopCamera();
            setCurrentView('home');
          }}
        >
          ← Back
        </button>
        <h2>Take Food Photo</h2>
      </div>

      <div className="camera-container">
        <video 
          ref={videoRef}
          autoPlay 
          playsInline
          style={{ display: cameraActive ? 'block' : 'none' }}
        />
        <canvas 
          ref={canvasRef} 
          style={{ display: 'none' }}
        />
        
        {!cameraActive && (
          <div className="camera-placeholder">
            <p>Camera not active</p>
            <button className="btn-primary" onClick={startCamera}>
              Start Camera
            </button>
          </div>
        )}
      </div>

      {cameraActive && (
        <div className="camera-controls">
          <button 
            className="btn-capture"
            onClick={capturePhoto}
          >
            📸 Capture Photo
          </button>
        </div>
      )}
    </div>
  );

  const renderAnalysis = () => (
    <div className="analysis-view">
      <div className="analysis-header">
        <button 
          className="btn-back"
          onClick={() => setCurrentView('camera')}
        >
          ← Back
        </button>
        <h2>Food Analysis</h2>
      </div>

      <div className="analysis-container">
        {capturedImage && (
          <div className="captured-image">
            <img src={capturedImage} alt="Captured food" />
          </div>
        )}

        <div className="weight-input">
          <label>Estimated Weight (grams):</label>
          <input
            type="number"
            value={weightGrams}
            onChange={(e) => setWeightGrams(Number(e.target.value))}
            min="1"
            max="2000"
          />
          {bluetoothConnected && (
            <p className="bluetooth-help">
              📡 Weight will be updated automatically from your connected scale
            </p>
          )}
        </div>

        {!foodAnalysis && (
          <button 
            className="btn-primary"
            onClick={analyzeFood}
            disabled={analyzing}
          >
            {analyzing ? 'Analyzing...' : 'Analyze Food'}
          </button>
        )}

        {foodAnalysis && (
          <div className="analysis-results">
            <div className="food-info">
              <h3>{foodAnalysis.food_name}</h3>
              <p className="confidence">Confidence: {Math.round(foodAnalysis.confidence * 100)}%</p>
            </div>

            <div className="nutrition-card">
              <div className="nutrition-item main">
                <span className="nutrition-label">Total Calories</span>
                <span className="nutrition-value">{foodAnalysis.total_calories} cal</span>
              </div>
              <div className="nutrition-grid">
                <div className="nutrition-item">
                  <span className="nutrition-label">Protein</span>
                  <span className="nutrition-value">{foodAnalysis.protein}g</span>
                </div>
                <div className="nutrition-item">
                  <span className="nutrition-label">Carbs</span>
                  <span className="nutrition-value">{foodAnalysis.carbs}g</span>
                </div>
                <div className="nutrition-item">
                  <span className="nutrition-label">Fat</span>
                  <span className="nutrition-value">{foodAnalysis.fat}g</span>
                </div>
              </div>
            </div>

            <button 
              className="btn-primary"
              onClick={logFood}
            >
              Log This Food
            </button>
          </div>
        )}
      </div>
    </div>
  );

  const renderLogs = () => (
    <div className="logs-view">
      <div className="logs-header">
        <button 
          className="btn-back"
          onClick={() => setCurrentView('home')}
        >
          ← Back
        </button>
        <h2>Today's Food Log</h2>
      </div>

      <div className="logs-summary">
        <div className="summary-card">
          <h3>Daily Totals</h3>
          <div className="summary-grid">
            <div className="summary-item">
              <span className="summary-label">Calories</span>
              <span className="summary-value">{Math.round(dailyTotals.calories)}</span>
            </div>
            <div className="summary-item">
              <span className="summary-label">Protein</span>
              <span className="summary-value">{dailyTotals.protein}g</span>
            </div>
            <div className="summary-item">
              <span className="summary-label">Carbs</span>
              <span className="summary-value">{dailyTotals.carbs}g</span>
            </div>
            <div className="summary-item">
              <span className="summary-label">Fat</span>
              <span className="summary-value">{dailyTotals.fat}g</span>
            </div>
          </div>
        </div>
      </div>

      <div className="logs-list">
        {foodLogs.length === 0 ? (
          <div className="no-logs">
            <p>No food logged today</p>
            <button 
              className="btn-primary"
              onClick={() => setCurrentView('camera')}
            >
              Log Your First Meal
            </button>
          </div>
        ) : (
          foodLogs.map(log => (
            <div key={log.log_id} className="log-item">
              <div className="log-image">
                <img src={log.image_base64} alt={log.food_name} />
              </div>
              <div className="log-info">
                <h4>{log.food_name}</h4>
                <p>{log.weight_grams}g • {Math.round(log.total_calories)} calories</p>
                <div className="log-macros">
                  <span>P: {log.protein}g</span>
                  <span>C: {log.carbs}g</span>
                  <span>F: {log.fat}g</span>
                </div>
              </div>
              <button 
                className="btn-delete"
                onClick={() => deleteLog(log.log_id)}
              >
                🗑️
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );

  // Authentication check
  if (!isAuthenticated) {
    return (
      <div className="App">
        {currentView === 'login' && renderLogin()}
        {currentView === 'register' && renderRegister()}
        {currentView !== 'login' && currentView !== 'register' && setCurrentView('login')}
      </div>
    );
  }

  return (
    <div className="App">
      {currentView === 'home' && renderHome()}
      {currentView === 'camera' && renderCamera()}
      {currentView === 'analysis' && renderAnalysis()}
      {currentView === 'logs' && renderLogs()}
      {currentView === 'stats' && renderStats()}
    </div>
  );
}

export default App;