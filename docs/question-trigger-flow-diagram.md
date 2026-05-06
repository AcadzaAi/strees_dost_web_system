# Question Trigger Decision Flow - Visual Diagrams

## System Overview

```mermaid
graph TB
    A[User Opens App] --> B{Check User Type}
    B -->|New User| C[Ask for Name]
    B -->|Returning User| D[Load Profile]
    C --> E[Save Name to Storage]
    E --> F[Generate Test Plan]
    D --> F
    F --> G{User Type?}
    G -->|New| H[Fixed Sequence<br/>Q1-Q7 predetermined]
    G -->|Returning| I[Random Sequence<br/>Q1 always medium<br/>Q2-Q7 randomized]
    H --> J[Fetch Questions<br/>5 medium + 2 hard]
    I --> J
    J --> K[Render Questions<br/>with Triggers]
    K --> L[User Completes Test]
    L --> M[Save Results<br/>test_count++<br/>previous_triggers]
    M --> N[End]
```

## New User Flow

```mermaid
sequenceDiagram
    participant U as User
    participant F as Frontend
    participant A as API
    participant D as Decision Engine
    participant S as Storage

    U->>F: Open App
    F->>S: Load Profile
    S-->>F: Empty Profile
    F->>A: POST /check-user-type
    A->>D: is_new_user(profile)
    D-->>A: true
    A-->>F: is_new_user: true
    F->>U: Show Name Input
    U->>F: Enter Name
    F->>S: Save Name
    F->>A: POST /trigger-plan
    A->>D: get_full_test_plan(profile)
    D-->>A: Fixed Sequence (Q1-Q7)
    A-->>F: Test Plan
    F->>A: POST /load-test-questions (medium, 5)
    A-->>F: 5 Medium Questions
    F->>A: POST /load-test-questions (hard, 2)
    A-->>F: 2 Hard Questions
    F->>U: Render Q1 with SPOTLIGHT_HUNT
    U->>F: Answer Q1
    F->>U: Render Q2 with HARD_FOG
    Note over F,U: Continue through Q7
    U->>F: Complete Test
    F->>S: Save Results (test_count=1)
```

## Returning User Flow

```mermaid
sequenceDiagram
    participant U as User
    participant F as Frontend
    participant A as API
    participant D as Decision Engine
    participant S as Storage

    U->>F: Open App
    F->>S: Load Profile
    S-->>F: {name: "John", test_count: 5}
    F->>A: POST /check-user-type
    A->>D: is_new_user(profile)
    D-->>A: false
    A-->>F: is_new_user: false
    Note over F,U: Skip Name Input
    F->>A: POST /trigger-plan
    A->>D: get_full_test_plan(profile, previous_triggers)
    D-->>A: Random Sequence (Q1 medium, Q2-Q7 random)
    A-->>F: Test Plan
    F->>A: POST /load-test-questions (medium, 5)
    A-->>F: 5 Medium Questions
    F->>A: POST /load-test-questions (hard, 2)
    A-->>F: 2 Hard Questions
    F->>U: Render Questions with Random Triggers
    U->>F: Complete Test
    F->>S: Save Results (test_count=6, previous_triggers)
```

## Decision Engine Logic

```mermaid
flowchart TD
    A[get_full_test_plan] --> B{is_new_user?}
    B -->|Yes| C[get_trigger_sequence_for_new_user]
    B -->|No| D[get_trigger_sequence_for_returning_user]
    
    C --> E[Return Fixed Sequence]
    E --> E1[Q1: SPOTLIGHT_HUNT]
    E1 --> E2[Q2: HARD_FOG]
    E2 --> E3[Q3: FLIP_CYCLE hard]
    E3 --> E4[Q4: ACCURACY_TEST]
    E4 --> E5[Q5: READING_TEST]
    E5 --> E6[Q6: HARD_PEER_DOUBT hard]
    E6 --> E7[Q7: BILLIARD_BALL]
    
    D --> F[Shuffle Medium Pool]
    F --> G[Shuffle Hard Pool]
    G --> H[Q1: Pick Medium never hard]
    H --> I[Q2-Q7: Random 2 hard + 4 medium]
    I --> J[Avoid Last Trigger if possible]
    J --> K[Return Random Sequence]
    
    E7 --> L[Validate Sequence]
    K --> L
    L --> M{Valid?}
    M -->|Yes| N[Return Test Plan]
    M -->|No| O[Raise Error]
```

## Trigger Selection for Returning Users

```mermaid
flowchart LR
    A[Start] --> B[Q1: Select Medium]
    B --> C{Previous Test?}
    C -->|Yes| D[Deprioritize Last Trigger]
    C -->|No| E[Random Medium]
    D --> E
    E --> F[Q2-Q7: Select Positions]
    F --> G[Pick 2 Random Positions from 2-7]
    G --> H[Assign Hard Triggers to Positions]
    H --> I[Fill Remaining with Medium]
    I --> J[Shuffle Within Constraints]
    J --> K[Validate: 2 hard + 5 medium]
    K --> L{Valid?}
    L -->|Yes| M[Return Sequence]
    L -->|No| F
```

## Validation Flow

```mermaid
flowchart TD
    A[Validate Sequence] --> B{Length = 7?}
    B -->|No| Z[Error: Wrong Length]
    B -->|Yes| C{Q1 is Medium?}
    C -->|No| Y[Error: Q1 Cannot Be Hard]
    C -->|Yes| D{Count Hard = 2?}
    D -->|No| X[Error: Must Have 2 Hard]
    D -->|Yes| E{Count Medium = 5?}
    E -->|No| W[Error: Must Have 5 Medium]
    E -->|Yes| F{All Triggers Valid?}
    F -->|No| V[Error: Invalid Trigger Name]
    F -->|Yes| G{No Duplicates?}
    G -->|No| U[Error: Duplicate Triggers]
    G -->|Yes| H[✅ Valid Sequence]
```

## Trigger Intensity Progression (New Users)

```mermaid
gantt
    title Trigger Intensity Over 7 Questions (New Users)
    dateFormat X
    axisFormat %s

    section Intensity
    Mild (Q1)           :0, 1
    Strong (Q2)         :1, 2
    Strong Hard (Q3)    :crit, 2, 3
    Moderate (Q4)       :3, 4
    Moderate (Q5)       :4, 5
    Strong Hard (Q6)    :crit, 5, 6
    Moderate (Q7)       :6, 7
```

## API Endpoint Architecture

```mermaid
graph LR
    A[Frontend] --> B[API Layer]
    B --> C[/check-user-type]
    B --> D[/trigger-plan]
    B --> E[/trigger/question_number]
    
    C --> F[Decision Engine]
    D --> F
    E --> F
    
    F --> G[is_new_user]
    F --> H[get_full_test_plan]
    F --> I[get_trigger_for_question]
    
    G --> J[User Profile]
    H --> J
    I --> J
    
    J --> K[Constants]
    K --> L[QUESTION_TRIGGERS]
    K --> M[QUESTION_TRIGGER_META]
    K --> N[NEW_USER_TRIGGER_SEQUENCE]
```

## Data Flow

```mermaid
flowchart TB
    subgraph Frontend
        A[User Profile<br/>SharedPreferences]
        B[Test Plan<br/>State]
        C[Questions<br/>Array]
        D[Trigger Configs<br/>Array]
    end
    
    subgraph Backend
        E[API Endpoints]
        F[Decision Engine]
        G[Constants]
        H[Question Fetcher]
    end
    
    A -->|POST /check-user-type| E
    E -->|is_new_user| A
    
    A -->|POST /trigger-plan| E
    E --> F
    F --> G
    F -->|Test Plan| B
    
    B -->|POST /load-test-questions| E
    E --> H
    H -->|Questions| C
    
    B -->|Trigger Configs| D
    C -->|Questions| D
    D -->|Render| Frontend
```

## Trigger Application Timeline

```mermaid
timeline
    title Question Progression with Triggers
    Q1 : SPOTLIGHT_HUNT (medium)
       : Visual focus test
       : Mild intensity
    Q2 : HARD_FOG (medium)
       : Fog overlay + meta-question
       : Strong intensity
    Q3 : FLIP_CYCLE (hard)
       : Screen flip cycle
       : Strong intensity
       : ⚠️ HARD QUESTION
    Q4 : ACCURACY_TEST (medium)
       : Precision challenge
       : Moderate intensity
    Q5 : READING_TEST (medium)
       : Reading comprehension
       : Moderate intensity
    Q6 : HARD_PEER_DOUBT (hard)
       : Peer comparison
       : Strong intensity
       : ⚠️ HARD QUESTION
    Q7 : BILLIARD_BALL (medium)
       : Moving target tracking
       : Moderate intensity
```

## State Machine

```mermaid
stateDiagram-v2
    [*] --> CheckUserType
    CheckUserType --> NewUser: name empty OR test_count = 0
    CheckUserType --> ReturningUser: name exists AND test_count > 0
    
    NewUser --> AskName
    AskName --> SaveName
    SaveName --> GenerateFixedPlan
    
    ReturningUser --> LoadProfile
    LoadProfile --> GenerateRandomPlan
    
    GenerateFixedPlan --> FetchQuestions
    GenerateRandomPlan --> FetchQuestions
    
    FetchQuestions --> RenderQ1
    RenderQ1 --> RenderQ2
    RenderQ2 --> RenderQ3
    RenderQ3 --> RenderQ4
    RenderQ4 --> RenderQ5
    RenderQ5 --> RenderQ6
    RenderQ6 --> RenderQ7
    RenderQ7 --> SaveResults
    SaveResults --> [*]
```

## Constraint Enforcement

```mermaid
mindmap
  root((Constraints))
    Total Questions
      Exactly 7
    Q1 Rule
      Never Hard
      Always Medium
    Hard Questions
      Exactly 2
      Q2-Q7 only
      FLIP_CYCLE
      HARD_PEER_DOUBT
    Medium Questions
      Exactly 5
      Any position
      5 trigger types
    No Duplicates
      Each trigger once
      Unique per test
    Repetition Avoidance
      Deprioritize last
      From previous test
```

## Error Handling Flow

```mermaid
flowchart TD
    A[API Request] --> B{Valid Request?}
    B -->|No| C[400 Bad Request]
    B -->|Yes| D[Process Request]
    D --> E{User Profile Valid?}
    E -->|No| F[400 Invalid Profile]
    E -->|Yes| G[Generate Sequence]
    G --> H{Validation Pass?}
    H -->|No| I[500 Validation Error]
    H -->|Yes| J[Return Success]
    
    C --> K[Error Response]
    F --> K
    I --> K
    J --> L[Success Response]
```

## Performance Optimization

```mermaid
graph LR
    A[Request] --> B{Cached?}
    B -->|Yes| C[Return Cached]
    B -->|No| D[Generate New]
    D --> E[Validate]
    E --> F[Cache Result]
    F --> G[Return Result]
    C --> H[Fast Response]
    G --> I[Normal Response]
```

## Integration Points

```mermaid
graph TB
    subgraph Frontend
        A[React/JS App]
        B[SharedPreferences]
        C[UI Components]
    end
    
    subgraph Backend
        D[Flask API]
        E[Decision Engine]
        F[Question Service]
    end
    
    subgraph External
        G[Acadza API]
    end
    
    A <-->|User Profile| B
    A <-->|API Calls| D
    D <-->|Logic| E
    D <-->|Questions| F
    F <-->|Fetch| G
    A -->|Render| C
```

## Legend

- 🟢 **Green**: Success path
- 🔴 **Red/Critical**: Hard questions or errors
- 🟡 **Yellow**: Medium questions
- ⚠️ **Warning**: Important constraints
- ✅ **Check**: Validation passed
- ❌ **Cross**: Validation failed

