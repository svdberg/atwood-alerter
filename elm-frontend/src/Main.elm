port module Main exposing (main)

import Browser
import Browser.Dom
import Browser.Events
import Config exposing (apiBaseUrl)
import Css
import DateHelper exposing (cutOffTralingZeroes, diffDatesInDays, formatAsRssStyle)
import Element exposing (..)
import Element.Background as Background
import Element.Border as Border
import Element.Events as ElementEvents
import Element.Font as Font
import Element.Input as Input
import Element.Region as Region
import Html.Attributes as HtmlAttr
import Html.Events as HtmlEvents
import Html.Styled as Html
import Html.Styled.Attributes as Attr
import Html.Styled.Events as Events
import Http
import Json.Decode as Decode exposing (Decoder, field, string)
import Json.Encode
import Process
import SignupModal exposing (StatusMsg(..))
import Tailwind.Theme as Twt
import Tailwind.Utilities as Tw
import Task



-- MODEL


type alias Model =
    { status : RemoteData
    , email : String
    , statusMsg : StatusMsg
    , pushStatus : PushStatus
    , signupOpen : Bool
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
    , sold : Bool
    }


init : () -> ( Model, Cmd Msg )
init _ =
    ( { status = Loading, email = "", statusMsg = Idle, pushStatus = PushIdle, signupOpen = False }
    , Cmd.batch [ fetchStatus, scheduleTick ]
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
    | OpenSignup
    | CloseSignup
    | NoOp


fetchStatus : Cmd Msg
fetchStatus =
    Http.get
        { url = apiBaseUrl ++ "/status"
        , expect = Http.expectJson GotStatus statusDecoder
        }


statusDecoder : Decoder StatusData
statusDecoder =
    Decode.map6 StatusData
        (field "last_run_time" string)
        (field "last_seen_post" (field "title" string))
        (field "last_seen_post" (field "url" string))
        (field "last_seen_post" (field "published" string))
        (field "last_seen_post" (field "image_url" string))
        (field "last_seen_post" (field "sold" Decode.bool))



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
            if model.statusMsg == Sending then
                ( model, Cmd.none )

            else
                submit model

        GotSubscriptionResult result ->
            let
                ok =
                    case result of
                        Ok _ ->
                            True

                        Err _ ->
                            False
            in
            ( applyState (SignupModal.onSubscribeResult ok (toState model)) model, Cmd.none )

        Tick ->
            ( model, fetchStatus )

        RequestPushRegistration ->
            ( { model | pushStatus = PushRequesting }
            , requestPushRegistration ()
            )

        PushPermissionResult status ->
            ( { model | pushStatus = status }, subscribeToPush () )

        OpenSignup ->
            ( applyState (SignupModal.openModal (toState model)) model
            , Task.attempt (\_ -> NoOp) (Browser.Dom.focus "signup-email")
            )

        CloseSignup ->
            ( applyState (SignupModal.closeModal (toState model)) model
            , Task.attempt (\_ -> NoOp) (Browser.Dom.focus "get-alerts")
            )

        NoOp ->
            ( model, Cmd.none )


toState : Model -> SignupModal.State
toState model =
    { open = model.signupOpen, email = model.email, statusMsg = model.statusMsg }


applyState : SignupModal.State -> Model -> Model
applyState state model =
    { model | signupOpen = state.open, email = state.email, statusMsg = state.statusMsg }


submit : Model -> ( Model, Cmd Msg )
submit model =
    let
        body =
            Http.jsonBody (Json.Encode.object [ ( "email", Json.Encode.string model.email ) ])

        request =
            Http.post
                { url = apiBaseUrl ++ "/subscribe"
                , body = body
                , expect = Http.expectString GotSubscriptionResult
                }
    in
    ( { model | statusMsg = Sending }, request )



-- PORTS


port requestPushRegistration : () -> Cmd msg


port pushRegistrationResponse : (String -> msg) -> Sub msg


port subscribeToPush : () -> Cmd msg



-- VIEW


slate800 : Color
slate800 =
    rgb255 30 41 59


slate500 : Color
slate500 =
    rgb255 100 116 139


blue600 : Color
blue600 =
    rgb255 37 99 235


green700 : Color
green700 =
    rgb255 4 120 87


red700 : Color
red700 =
    rgb255 185 28 28


view : Model -> Element Msg
view model =
    column
        ([ width fill
         , height (minimum 0 fill)
         , Background.color (rgb255 245 248 255)
         ]
            ++ (if model.signupOpen then
                    [ inFront (viewModal model) ]

                else
                    []
               )
        )
        [ column
            ([ centerX
             , width (fill |> maximum 640)
             , spacing 24
             , padding 20
             ]
                ++ (if model.signupOpen then
                        [ htmlAttribute (HtmlAttr.attribute "aria-hidden" "true")
                        , htmlAttribute (HtmlAttr.attribute "inert" "")
                        ]

                    else
                        []
                   )
            )
            [ wrappedRow [ width fill, spacing 12 ]
                [ el
                    [ Region.heading 1
                    , Font.size 28
                    , Font.bold
                    , Font.color slate800
                    , alignLeft
                    ]
                    (Element.text "Atwood Sniper!")
                , el [ alignRight ] getAlertsButton
                ]
            , viewStatus model.status
            ]
        ]


cardAttrs : List (Attribute msg)
cardAttrs =
    [ Background.color (rgb255 255 255 255)
    , Border.rounded 12
    , Border.shadow { offset = ( 0, 4 ), blur = 12, color = rgba255 0 0 0 0.1, size = 1 }
    , padding 24
    , spacing 20
    , width fill
    ]


viewStatus : RemoteData -> Element Msg
viewStatus remote =
    case remote of
        NotAsked ->
            column cardAttrs []

        Loading ->
            column (cardAttrs ++ [ height (minimum 140 shrink) ])
                [ el [ Font.color slate500 ] (Element.text "Loading latest release...") ]

        Failure _ ->
            column (cardAttrs ++ [ spacing 8 ])
                [ el [ Font.color red700 ] (Element.text "Could not load the latest release.")
                , el [ Font.size 14, Font.color slate500 ] (Element.text "We'll retry automatically in a minute.")
                ]

        Success s ->
            column cardAttrs
                [ el
                    [ Font.size 13
                    , Font.color slate500
                    , Font.letterSpacing 1
                    ]
                    (Element.text "LATEST RELEASE")
                , row [ spacing 16, width fill ]
                    [ if String.isEmpty s.lastPostImageUrl then
                        none

                      else
                        Element.image
                            [ Element.width (px 80)
                            , Element.height (px 80)
                            , Element.clip
                            , Border.rounded 8
                            , alignTop
                            ]
                            { src = s.lastPostImageUrl
                            , description = ""
                            }
                    , column [ width fill, spacing 8, alignTop ]
                        [ paragraph [ width fill ]
                            [ newTabLink
                                [ htmlAttribute (HtmlAttr.attribute "aria-label" (s.lastPostTitle ++ " (opens in new tab)")) ]
                                { label =
                                    el
                                        [ Font.underline
                                        , Font.color blue600
                                        , Font.medium
                                        , Font.size 18
                                        ]
                                        (Element.text s.lastPostTitle)
                                , url = s.lastPostUrl
                                }
                            ]
                        , el
                            [ alignLeft
                            , paddingXY 10 4
                            , Background.color
                                (if s.sold then
                                    rgb255 254 226 226

                                 else
                                    rgb255 209 250 229
                                )
                            , Font.color
                                (if s.sold then
                                    rgb255 153 27 27

                                 else
                                    green700
                                )
                            , Border.rounded 999
                            , Font.size 14
                            , Font.semiBold
                            ]
                            (Element.text
                                (if s.sold then
                                    "Sold Out"

                                 else
                                    "Available"
                                )
                            )
                        , el [ Font.size 14, Font.color slate500 ]
                            (Element.text (cutOffTralingZeroes s.lastPostDate))
                        ]
                    ]
                , wrappedRow
                    [ width fill
                    , spacing 24
                    , Border.widthEach { top = 1, right = 0, bottom = 0, left = 0 }
                    , Border.color (rgb255 226 232 240)
                    , paddingEach { top = 16, right = 0, bottom = 0, left = 0 }
                    , Font.size 14
                    , Font.color slate500
                    ]
                    [ Element.text ("Last checked: " ++ cutOffTralingZeroes (formatAsRssStyle s.lastChecked))
                    , Element.text ("Days since last tool release: " ++ diffDatesInDays s.lastChecked s.lastPostDate)
                    ]
                ]


viewModal : Model -> Element Msg
viewModal model =
    el
        [ width fill
        , height fill
        , Background.color (rgba255 15 23 42 0.5)
        , ElementEvents.onClick CloseSignup
        , inFront
            (el
                [ centerX
                , centerY
                , width (fill |> maximum 420)
                , paddingXY 16 0
                ]
                (viewDialog model)
            )
        ]
        none


viewDialog : Model -> Element Msg
viewDialog model =
    column
        [ width fill
        , height (shrink |> maximum 640)
        , scrollbarY
        , Background.color (rgb255 255 255 255)
        , Border.rounded 12
        , padding 24
        , spacing 16
        , Border.shadow { offset = ( 0, 10 ), blur = 30, size = 0, color = rgba255 0 0 0 0.25 }
        , htmlAttribute (HtmlAttr.attribute "role" "dialog")
        , htmlAttribute (HtmlAttr.attribute "aria-modal" "true")
        , htmlAttribute (HtmlAttr.attribute "aria-labelledby" "signup-title")
        , htmlAttribute (HtmlEvents.stopPropagationOn "click" (Decode.succeed ( NoOp, True )))
        ]
        [ row [ width fill, spacing 12 ]
            [ paragraph
                [ Region.heading 2
                , htmlAttribute (HtmlAttr.id "signup-title")
                , Font.size 20
                , Font.bold
                , Font.color slate800
                ]
                [ Element.text "Get notified of new releases" ]
            , closeButton
            ]
        , paragraph [ Font.size 14, Font.color slate500 ]
            [ Element.text "We'll email you when a new Atwood release is posted." ]
        , Input.email
            [ width fill
            , Border.color slate500
            , Border.width 1
            , Border.rounded 8
            , padding 12
            , Font.size 16
            , htmlAttribute (HtmlAttr.id "signup-email")
            , htmlAttribute (HtmlAttr.attribute "autocomplete" "email")
            , htmlAttribute (HtmlAttr.attribute "inputmode" "email")
            , htmlAttribute (HtmlEvents.on "keydown" (SignupModal.enterDecoder Submit))
            ]
            { onChange = UpdateEmail
            , text = model.email
            , placeholder = Just (Input.placeholder [] (Element.text "you@example.com"))
            , label =
                Input.labelAbove [ Font.size 14, Font.color (rgb255 51 65 85) ]
                    (Element.text "Email address")
            }
        , formButton (model.statusMsg == Sending)
            (if model.statusMsg == Sending then
                "Subscribing..."

             else
                "Subscribe"
            )
            Submit
        , el [ width fill, Region.announce ] (viewStatusMsg model.statusMsg)
        , el
            [ width fill
            , Border.widthEach { top = 1, right = 0, bottom = 0, left = 0 }
            , Border.color (rgb255 226 232 240)
            ]
            none
        , viewPushSection model.pushStatus
        ]


closeButton : Element Msg
closeButton =
    Html.button
        [ Events.onClick CloseSignup
        , Attr.type_ "button"
        , Attr.attribute "aria-label" "Close"
        , Attr.css
            [ Css.width (Css.px 44)
            , Css.height (Css.px 44)
            , Css.fontSize (Css.px 24)
            , Css.color (Css.rgb 100 116 139)
            , Css.backgroundColor Css.transparent
            , Css.border (Css.px 0)
            , Css.cursor Css.pointer
            , focusRing
            ]
        ]
        [ Html.text "×" ]
        |> Html.toUnstyled
        |> Element.html
        |> el [ alignTop, alignRight ]


viewStatusMsg : StatusMsg -> Element msg
viewStatusMsg status =
    case status of
        Idle ->
            none

        Sending ->
            el [ Font.color (rgb255 71 85 105) ] (Element.text "Sending...")

        Sent msg ->
            paragraph [ Font.color green700 ] [ Element.text ("✓ " ++ msg) ]

        Error msg ->
            paragraph [ Font.color red700 ]
                [ Element.text ("! " ++ msg ++ " Please check the address and try again.") ]


viewPushSection : PushStatus -> Element Msg
viewPushSection status =
    case status of
        PushGranted ->
            paragraph [ Font.color green700 ] [ Element.text "✓ Push notifications are on." ]

        _ ->
            column [ width fill, spacing 8 ]
                [ el [ Region.heading 3, Font.size 18, Font.bold, Font.color slate800 ] (Element.text "Push Notifications")
                , case status of
                    PushRequesting ->
                        el [ Font.color slate500 ] (Element.text "Requesting permission...")

                    PushDenied ->
                        column [ width fill, spacing 8 ]
                            [ paragraph [ Font.color red700 ]
                                [ Element.text "Push permission denied. Allow notifications for this site in your browser settings, then try again." ]
                            , pushButton
                            ]

                    PushFailed msg ->
                        column [ width fill, spacing 8 ]
                            [ paragraph [ Font.color red700 ]
                                [ Element.text ("Push registration failed: " ++ msg) ]
                            , pushButton
                            ]

                    _ ->
                        pushButton
                ]


pushButton : Element Msg
pushButton =
    styledButton "Enable Push Notifications" RequestPushRegistration


focusRing : Css.Style
focusRing =
    Css.focus
        [ Css.outline3 (Css.px 2) Css.solid (Css.rgb 37 99 235)
        , Css.outlineOffset (Css.px 2)
        ]


getAlertsButton : Element Msg
getAlertsButton =
    Html.button
        [ Events.onClick OpenSignup
        , Attr.type_ "button"
        , Attr.id "get-alerts"
        , Attr.css
            [ Tw.bg_color Twt.blue_600
            , Tw.text_color Twt.white
            , Tw.px_4
            , Tw.py_2
            , Tw.rounded
            , Tw.font_medium
            , Css.cursor Css.pointer
            , focusRing
            ]
        ]
        [ Html.text "Get alerts" ]
        |> Html.toUnstyled
        |> Element.html


styledButton : String -> msg -> Element msg
styledButton label handler =
    formButton False label handler


formButton : Bool -> String -> msg -> Element msg
formButton isDisabled label handler =
    Html.button
        [ Events.onClick handler
        , Attr.type_ "button"
        , Attr.disabled isDisabled
        , Attr.css
            ([ Tw.bg_color Twt.blue_600
             , Tw.text_color Twt.white
             , Tw.px_4
             , Tw.py_3
             , Tw.rounded
             , Tw.font_medium
             , Tw.w_full
             , focusRing
             ]
                ++ (if isDisabled then
                        [ Tw.opacity_60, Tw.cursor_not_allowed ]

                    else
                        [ Css.cursor Css.pointer ]
                   )
            )
        ]
        [ Html.text label ]
        |> Html.toUnstyled
        |> Element.html



-- SUBSCRIPTIONS


subscriptions : Model -> Sub Msg
subscriptions model =
    Sub.batch
        [ pushRegistrationResponse pushResponseToMsg
        , if model.signupOpen then
            Browser.Events.onKeyDown (SignupModal.escapeDecoder CloseSignup)

          else
            Sub.none
        ]


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
