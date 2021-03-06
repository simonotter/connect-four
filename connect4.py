import endpoints
from google.appengine.ext import ndb
from protorpc import remote, messages
from models import (
    User,
    Game,
    Score,
    StringMessage,
    NewGameForm,
    GameForm,
    GameForms,
    MakeMoveForm,
    ScoreForms,
    UserRankForms,
    UserRank,
    History,
    HistoryForms)
from utils import get_by_urlsafe

API_EXPLORER_CLIENT_ID = endpoints.API_EXPLORER_CLIENT_ID
EMAIL_SCOPE = endpoints.EMAIL_SCOPE

USER_REQUEST = endpoints.ResourceContainer(
    user_name=messages.StringField(1, required=True),
    email=messages.StringField(2, required=True))

NEW_GAME_REQUEST = endpoints.ResourceContainer(NewGameForm)

GET_GAME_REQUEST = endpoints.ResourceContainer(
    urlsafe_game_key=messages.StringField(1), )

CANCEL_GAME_REQUEST = endpoints.ResourceContainer(
    user_name=messages.StringField(1, required=True),
    urlsafe_game_key=messages.StringField(2), )

GET_USER_GAMES_REQUEST = endpoints.ResourceContainer(
    user_name=messages.StringField(1))

MAKE_MOVE_REQUEST = endpoints.ResourceContainer(
    MakeMoveForm,
    urlsafe_game_key=messages.StringField(1), )

GET_SCORES_REQUEST = endpoints.ResourceContainer(
    quantity_of_scores=messages.IntegerField(1),)


@endpoints.api(name='connect4',
               version='v1',
               allowed_client_ids=[API_EXPLORER_CLIENT_ID],
               scopes=[EMAIL_SCOPE])
class ConnectFourApi(remote.Service):
    """Connect Four Game API v0.1"""

    @endpoints.method(request_message=USER_REQUEST,
                      response_message=StringMessage,
                      path='user',
                      name='create_user',
                      http_method='POST')
    def create_user(self, request):
        """Create a User. Requires a unique username"""
        if User.query(User.name == request.user_name).get():
            raise endpoints.ConflictException(
                'A User with that name already exists!')
        user = User(name=request.user_name, email=request.email)
        user.put()
        return StringMessage(message='User {} created!'.format(
            request.user_name))

    @endpoints.method(request_message=NEW_GAME_REQUEST,
                      response_message=GameForm,
                      path='game',
                      name='new_game',
                      http_method='POST')
    def new_game(self, request):
        """Creates a new Game"""
        try:
            game = Game.new_game(request.player1, request.player2)
        except ValueError:
            raise endpoints.BadRequestException('Invalid player objects')

        return game.to_form(
            "Good luck. It\'s %s\'s turn" % game.whose_turn.get().name)

    @endpoints.method(request_message=GET_GAME_REQUEST,
                      response_message=GameForm,
                      path='game/{urlsafe_game_key}',
                      name='get_game',
                      http_method='GET')
    def get_game(self, request):
        """Return the current game state."""
        game = get_by_urlsafe(request.urlsafe_game_key, Game)
        if game:
            if game.game_over:
                raise endpoints.ForbiddenException(
                    'Illegal action: Game is already over.')
            else:
                return game.to_form(
                    'Time to make a move, %s!' % game.whose_turn.get().name)
        else:
            raise endpoints.NotFoundException('Game not found!')

    @endpoints.method(request_message=MAKE_MOVE_REQUEST,
                      response_message=GameForm,
                      path='game/{urlsafe_game_key}',
                      name='make_move',
                      http_method='PUT')
    def make_move(self, request):
        """Makes a move. Returns a game state with message"""
        game = get_by_urlsafe(request.urlsafe_game_key, Game)
        if not game:
            raise endpoints.NotFoundException('Game not found!')

        if game.game_over:
            raise endpoints.ForbiddenException(
                'Illegal action: Game is already over.')

        # Check if column integer
        try:
            column = int(request.column)
        except ValueError:
            raise endpoints.BadRequestException(
                'Column must be a number between 1 and 7!')

        # validate the column input
        if not (1 <= column <= 7):
            raise endpoints.BadRequestException(
                'Column must be a number between 1 and 7!')

        # Check if the player is part of this game
        if request.player not in [game.player1.get().name,
                                  game.player2.get().name]:
            raise endpoints.ForbiddenException(
                'You are not part of this game')

        # Ensure it's this players turn
        if game.whose_turn.get().name != request.player:
            raise endpoints.UnauthorizedException(
                "It's not your turn, it's %s's!" % game.whose_turn.get().name)

        # Get token colour of current player
        if request.player == game.player1.get().name:
            colour = game.player1Colour
        else:
            colour = game.player2Colour

        if game.board.update(column, colour):

            # Log game history Record
            game.history.append(
                History(user=game.whose_turn,
                        column=column,
                        board_state_after_move=game.board.board))

            # Decrease attempts remaining
            game.holes_remaining -= 1

            # Check if game has been won
            if game.is_won():
                game.end_game(True)
                message = "%s has won the game!" % game.whose_turn.get().name

            else:
                if game.holes_remaining == 0:
                    game.end_game(False)
                    message = "Game Over - It's a draw"
                else:
                    # Update whose_turn to next player
                    game.switch_turn()
                    message = "Now it's %s's turn." % game.whose_turn.get().name

            # Store the updated game in ndb
            game.put()

        else:
            message = "This column is full, try another column"

        return game.to_form(message)

    @endpoints.method(request_message=GET_USER_GAMES_REQUEST,
                      response_message=GameForms,
                      path='user/{user_name}',
                      name='get_user_games',
                      http_method='GET')
    def get_user_games(self, request):
        """Returns all of a User's active games"""
        user = User.query().filter(User.name == request.user_name).get()
        if user:
            q = Game.query(ndb.AND(ndb.OR(Game.player1 == user.key,
                                          Game.player2 == user.key)),
                                  (Game.game_over != True))
            games = q.fetch()

            return GameForms(
                items=[game.to_form('') for game in games])
        else:
            raise endpoints.NotFoundException(
                'No user exists with that user name')

    @endpoints.method(request_message=CANCEL_GAME_REQUEST,
                      response_message=StringMessage,
                      path='game/{urlsafe_game_key}',
                      name='cancel_game',
                      http_method='DELETE')
    def cancel_game(self, request):
        """Cancel and delete the current game state."""
        game = get_by_urlsafe(request.urlsafe_game_key, Game)

        if game:  # game exits
            # check if user is a player in this game
            if request.user_name not in (game.player1.get().name,
                                         game.player2.get().name):
                raise endpoints.UnauthorizedException(
                    'You are not a player of this game')

            if game.game_over:
                user = game.whose_turn.get()
                message = """This game has ended. It was won by {user_name} and
                    cannot be cancelled""".format(user_name=user.name)
                return StringMessage(message=message)
            else:
                game.key.delete()
                return StringMessage(message='Game cancelled and deleted.')
        else:
            raise endpoints.NotFoundException('No game exists with that key!')

    @endpoints.method(request_message=GET_GAME_REQUEST,
                      response_message=HistoryForms,
                      path='game_history/{urlsafe_game_key}',
                      name='get_game_history',
                      http_method='GET')
    def get_game_history(self, request):
        """Get history of all moves by each player on a game."""
        game = get_by_urlsafe(request.urlsafe_game_key, Game)
        if not game:
            raise endpoints.NotFoundException("Game doesn't exist")

        return game.history_to_form()

    @endpoints.method(request_message=GET_SCORES_REQUEST,
                      response_message=ScoreForms,
                      path='scores',
                      name='get_high_scores',
                      http_method='GET')
    def get_high_scores(self, request):
        """Return all scores"""
        if request.quantity_of_scores:
            # check is positive integer
            if request.quantity_of_scores < 1:
                raise endpoints.BadRequestException(
                    'Quantity of Scores most be an positive integer')

            # return limited set of scores, according to quantity provided
            return ScoreForms(
                items=[score.to_form() for score in Score.query(
                ).order(-Score.holes_remaining).fetch(
                    request.quantity_of_scores)])

        else:  # no quantity provided, so return all scores
            return ScoreForms(items=[score.to_form()
                                     for score in Score.query().order(
                    -Score.holes_remaining)])

    @endpoints.method(response_message=UserRankForms,
                      path='rankings',
                      name='get_user_rankings',
                      http_method='GET')
    def get_user_rankings(self, request):
        """Returns list of user rankings"""
        return UserRankForms(items=[user_rank.to_form()
                                    for user_rank in UserRank.query().order(
                -UserRank.win_ratio)])

# registers API
api = endpoints.api_server([ConnectFourApi])
