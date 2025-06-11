port module Main exposing (main)

import Browser
import Http
import Json.Decode as Decode exposing (Decoder, string, field)
import Json.Encode
import Element exposing (..)
import Element.Background as Background
import Element.Border as Border
import Element.Font as Font
import Element.Input as Input
import Task
import Process
import DateHelper exposing (diffDatesInDays, formatAsRssStyle, cutOffTralingZeroes)
import Html.Styled as Html
import Html.Styled.Attributes as Attr
import Html.Styled.Events as Events
import Tailwind.Utilities as Tw
import Tailwind.Theme as Twt

-- MODEL

type alias Model =
    { status : RemoteData
    , email : String
    , statusMsg : StatusMsg
    , pushStatus : PushStatus
    }

type RemoteData
    = NotAsked
    | Loading
    | Success StatusData
    | Failure String

type PushStatus
    = PushIdle
    | PushRequesting
    | PushGranted
    | PushDenied
    | PushFailed String


type alias StatusData =
    { lastChecked : String
    , lastPostTitle : String
    , lastPostUrl : String
    , lastPostDate : String
    , lastPostImageUrl : String
    }

type StatusMsg
    = Idle
    | Sending
    | Sent String
    | Error String


init : () -> ( Model, Cmd Msg )
init _ =
    ( { status = Loading, email = "", statusMsg = Idle, pushStatus = PushIdle }
    , Cmd.batch [fetchStatus, scheduleTick]
    )

scheduleTick : Cmd Msg
scheduleTick =
    Process.sleep (60 * 1000)
        |> Task.perform (\_ -> Tick)

-- HTTP

type Msg
    = GotStatus (Result Http.Error StatusData)
    | UpdateEmail String
    | Submit
    | GotSubscriptionResult (Result Http.Error String)
    | Tick
    | RequestPushRegistration
    | PushPermissionResult PushStatus


fetchStatus : Cmd Msg
fetchStatus =
    Http.get
        { url = "https://b3q0v6btng.execute-api.eu-north-1.amazonaws.com/prod/status"
        , expect = Http.expectJson GotStatus statusDecoder
        }


statusDecoder : Decoder StatusData
statusDecoder =
    Decode.map5 StatusData
        (field "last_run_time" string)
        (field "last_seen_post" (field "title" string))
        (field "last_seen_post" (field "url" string))
        (field "last_seen_post" (field "published" string))
        (field "last_seen_post" (field "image_url" string))


-- UPDATE

update : Msg -> Model -> ( Model, Cmd Msg )
update msg model =
    case msg of
        GotStatus result ->
            case result of
                Ok data ->
                    ( { model | status = Success data }, scheduleTick )

                Err _ ->
                    ( { model | status = Failure "Could not load status." }, scheduleTick )

        UpdateEmail val ->
            ( { model | email = val }, Cmd.none )

        Submit ->
            let
                body =
                    Http.jsonBody (Json.Encode.object [ ( "email", Json.Encode.string model.email ) ])
                request =
                    Http.post
                        { url = "https://b3q0v6btng.execute-api.eu-north-1.amazonaws.com/prod/subscribe"                        
                        , body = body
                        , expect = Http.expectString GotSubscriptionResult
                        }
            in
            ( { model | statusMsg = Sending }, request )

        GotSubscriptionResult result ->
            case result of
                Ok _ ->
                    ( { model | statusMsg = Sent "Check your email to confirm!" }, Cmd.none )

                Err _ ->
                    ( { model | statusMsg = Error "Failed to subscribe." }, Cmd.none )
        
        Tick ->
            ( model, fetchStatus )

        RequestPushRegistration ->
            ( { model | pushStatus = PushRequesting }
            , requestPushRegistration ()
            )

        PushPermissionResult status ->
            ( { model | pushStatus = status }, subscribeToPush ())

-- PORTS

port requestPushRegistration : () -> Cmd msg


port pushRegistrationResponse : (String -> msg) -> Sub msg

port subscribeToPush : () -> Cmd msg

-- VIEW

view : Model -> Element Msg
view model =
    column
        [ spacing 20
        , padding 20
        , Background.color (rgb255 245 248 255)
        , width fill
        , Element.clip
        ]
        ([ el [ Font.size 24, Font.bold, width fill ] (Element.text "Atwood Sniper!")
         ]
            ++ viewStatus model.status
            ++ [ column
                [ Background.color (rgb255 255 255 255)
                , Border.rounded 10
                , Border.shadow { offset = ( 0, 4 ), blur = 12, color = rgba255 0 0 0 0.1, size = 1 }
                , padding 24
                , spacing 16
                , width fill
                ]
                [ el
                    [ Font.size 24
                    , Font.bold
                    , Font.color (rgb255 30 41 59) -- Tailwind slate-800
                    ]
                    (Element.text "📬 Subscribe to Alerts")

                , Input.email
                    [ width fill
                    , Border.color (rgb255 203 213 225) -- slate-300
                    , Border.rounded 8
                    , padding 12
                    , Font.size 16
                    ]
                    { onChange = UpdateEmail
                    , text = model.email
                    , placeholder = Just (Input.placeholder [] (Element.text "Enter your email"))
                    , label = Input.labelHidden "Email"
                    }

                , styledButton "Subscribe" Submit
                , viewStatusMsg model.statusMsg
                , viewPushSection model.pushStatus
                ]
            ]

        )


viewStatus : RemoteData -> List (Element Msg)
viewStatus remote =
    case remote of
        NotAsked ->
            []

        Loading ->
            [ Element.text "Loading status..." ]

        Failure err ->
            [ el [ Font.color (rgb255 200 0 0) ] (Element.text err) ]

        Success s ->
            [ column
                [ Background.color (rgb255 255 255 255)
                , Border.rounded 10
                , Border.shadow { offset = ( 0, 4 ), blur = 12, color = rgba255 0 0 0 0.1, size = 1 }
                , padding 24
                , spacing 16
                , width fill
                , Element.width (maximum 600 fill)  -- limit max card width
                ]
                [ el
                    [ Font.size 28
                    , Font.bold
                    , Font.color (rgb255 30 41 59)
                    ]
                    (Element.text "🪓 Atwood Blog Monitor")

                , el
                    [ Font.size 16
                    , Font.color (rgb255 100 116 139)
                    ]
                    (Element.text ("📅 Last checked: " ++ cutOffTralingZeroes(formatAsRssStyle s.lastChecked)))

                , el
                    [ Font.size 16
                    , Font.color (rgb255 100 116 139)
                    ]
                    (Element.text "🆕 Latest post:")

                , row
                [ spacing 12
                , alignLeft
                ]
                [ Element.image
                    [ Element.width (px 64)
                    , Element.height (px 64)
                    , Element.clip
                    , Border.rounded 6
                    ]
                    { src = s.lastPostImageUrl
                    , description = "Latest blog post image"
                    }
                , column [ spacing 4 ]
                    [ newTabLink []
                        { label =
                            el
                                [ Font.underline
                                , Font.color (rgb255 37 99 235) -- Tailwind blue-600
                                , Font.medium
                                , Font.size 16
                                ]
                                (Element.text s.lastPostTitle)
                        , url = s.lastPostUrl
                        }
                    , el
                        [ Font.size 14
                        , Font.color (rgb255 148 163 184) -- Tailwind slate-400
                        ]
                        (Element.text ("(" ++ cutOffTralingZeroes(s.lastPostDate) ++ ")"))
                    ]
                ]

                , paragraph 
                    [ width fill 
                    , Font.size 16
                    , Font.color (rgb255 100 116 139)
                    ]
                    [ Element.text ("Days since last tool release: " ++ diffDatesInDays s.lastChecked s.lastPostDate) ]
            ]
            ]


viewStatusMsg : StatusMsg -> Element msg
viewStatusMsg status =
    case status of
        Idle ->
            none

        Sending ->
            el [ Font.color (rgb255 100 100 100) ] (Element.text "Sending...")

        Sent msg ->
            el [ Font.color (rgb255 0 150 0) ] (Element.text msg)

        Error msg ->
            el [ Font.color (rgb255 200 0 0) ] (Element.text msg)

viewPushSection : PushStatus -> Element Msg
viewPushSection status =
    column [ width fill ]
        [ el [ Font.size 20, Font.bold ] (Element.text "Push Notifications")
        , case status of
            PushIdle ->
                styledButton "Enable Push Notifications" RequestPushRegistration
                
            PushRequesting ->
                el [] (Element.text "Requesting permission...")

            PushGranted ->
                el [] (Element.text "Push notifications enabled!")

            PushDenied ->
                el [ Font.color (rgb255 200 0 0) ] (Element.text "Push permission denied.")

            PushFailed msg ->
                el [ Font.color (rgb255 200 0 0) ] (Element.text ("Push registration failed: " ++ msg))
        ]

styledButton : String -> msg -> Element msg
styledButton label handler =
    Html.button
        [ Events.onClick handler
        , Attr.css
            [ Tw.bg_color Twt.blue_500
            , Tw.text_color Twt.white
            , Tw.px_4
            , Tw.py_2
            , Tw.rounded
            , Tw.w_full
            ]
        ]
        [ Html.text label ]
        |> Html.toUnstyled
        |> Element.html

-- SUBSCRIPTIONS


subscriptions : Model -> Sub Msg
subscriptions _ =
    pushRegistrationResponse pushResponseToMsg


pushResponseToMsg : String -> Msg
pushResponseToMsg str =
    case str of
        "granted" ->
            PushPermissionResult PushGranted

        "denied" ->
            PushPermissionResult PushDenied

        "failed" ->
            PushPermissionResult (PushFailed "Unknown error")

        other ->
            PushPermissionResult (PushFailed other)

-- MAIN

main : Program () Model Msg
main =
    Browser.element
        { init = init
        , update = update
        , view = view >> layout []
        , subscriptions = subscriptions
        }
